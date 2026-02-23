
# Talon — Integrations, Scheduler & File Sentinel

## Integration Base

All platform connectors implement `BaseIntegration`. Every platform routes
through the same `ChatRouter` — no platform-specific chat logic anywhere else.

```python
from abc import ABC, abstractmethod
from typing import Callable, Awaitable

class BaseIntegration(ABC):
    name: str
    enabled: bool = True

    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def stop(self): ...

    @abstractmethod
    async def send_message(self, channel: str, content: str): ...

    @abstractmethod
    async def on_message(self, callback: Callable[[dict], Awaitable[None]]): ...
```

## Discord Integration

```python
import discord
from .base import BaseIntegration

class DiscordIntegration(BaseIntegration):
    name = "discord"

    def __init__(self, token: str, guild_id: int, chat_router):
        intents = discord.Intents.default()
        intents.message_content = True
        self.client   = discord.Client(intents=intents)
        self.token    = token
        self.guild_id = guild_id
        self.chat_router = chat_router
        self._register_events()

    def _register_events(self):
        @self.client.event
        async def on_ready():
            log.info("discord_ready", guilds=len(self.client.guilds))

        @self.client.event
        async def on_message(message):
            if message.author == self.client.user: return
            if message.guild and message.guild.id != self.guild_id: return
            response = await self.chat_router.process(
                message=message.content,
                session_id=f"discord-{message.channel.id}-{message.author.id}",
                platform="discord",
            )
            await message.channel.send(response)

    async def start(self): await self.client.start(self.token)
    async def stop(self):  await self.client.close()
```

## Slack Integration (Socket Mode)

```python
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from .base import BaseIntegration

class SlackIntegration(BaseIntegration):
    name = "slack"

    def __init__(self, bot_token: str, app_token: str, chat_router):
        self.app         = AsyncApp(token=bot_token)
        self.handler     = AsyncSocketModeHandler(self.app, app_token)
        self.chat_router = chat_router
        self._register_handlers()

    def _register_handlers(self):
        @self.app.message()
        async def handle(message, say):
            response = await self.chat_router.process(
                message=message["text"],
                session_id=f"slack-{message['channel']}-{message['user']}",
                platform="slack",
            )
            await say(response)

    async def start(self): await self.handler.start_async()
    async def stop(self):  await self.handler.close_async()
```

## Scheduler (APScheduler)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

class TalonScheduler:
    def __init__(self, db_url: str):
        self.scheduler = AsyncIOScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=db_url)},
            job_defaults={"coalesce": True, "max_instances": 1,
                          "misfire_grace_time": 60}
        )

    def start(self): self.scheduler.start()
    def stop(self):  self.scheduler.shutdown(wait=False)

    def add_cron(self, job_id: str, func, cron_expr: str, **kw):
        self.scheduler.add_job(func, CronTrigger.from_crontab(cron_expr),
                               id=job_id, replace_existing=True, **kw)

    def add_interval(self, job_id: str, func, **interval_kw):
        self.scheduler.add_job(func, IntervalTrigger(**interval_kw),
                               id=job_id, replace_existing=True)

    def list_jobs(self) -> list[dict]:
        return [{"id": j.id, "next_run": str(j.next_run_time),
                 "trigger": str(j.trigger)} for j in self.scheduler.get_jobs()]
```

### Built-in Scheduled Jobs

```python
def register_builtin_jobs(scheduler, app_state):
    scheduler.add_cron("memory_recompile",    app_state.memory.recompile,    "0 * * * *")
    scheduler.add_interval("llm_health_sweep",app_state.gateway.health_sweep, minutes=5)
    scheduler.add_cron("log_rotate",          app_state.log_manager.rotate,  "0 2 * * *")
    scheduler.add_interval("working_memory_gc",app_state.memory.working.gc_idle, minutes=15)
    scheduler.add_cron("episodic_archive",    app_state.memory.episodic.archive_old, "0 3 * * *")
    scheduler.add_cron("session_cleanup",     app_state.session_manager.cleanup_stale, "*/30 * * * *")
```

## File Sentinel (watchdog)

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import asyncio

class SentinelHandler(FileSystemEventHandler):
    def __init__(self, router): self.router = router
    def on_any_event(self, event):
        if event.is_directory: return
        self.router.dispatch(event.event_type, Path(event.src_path))

class FileSentinel:
    def __init__(self, watch_paths, router):
        self.observer = Observer()
        handler = SentinelHandler(router)
        for path in watch_paths:
            self.observer.schedule(handler, str(path), recursive=True)

    def start(self): self.observer.start()
    def stop(self):  self.observer.stop(); self.observer.join()

class EventRouter:
    def __init__(self, registry, memory_engine, config_loader):
        self.registry = registry
        self.memory   = memory_engine
        self.config   = config_loader

    def dispatch(self, event_type: str, path: Path):
        if "skills" in path.parts and path.suffix == ".py":
            asyncio.create_task(self.registry.reload_skill(path.parent.name))
        elif path.parent.name == "memories" and path.suffix == ".md":
            asyncio.create_task(self.memory.recompile())
        elif path.name == "talon.toml":
            asyncio.create_task(self.config.reload())
```
