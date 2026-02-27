import { test, expect } from "@playwright/test"

test.describe("Chat Flow", () => {
  test("shows chat UI on load", async ({ page }) => {
    await page.goto("/")
    await expect(page.locator("text=Talon")).toBeVisible()
    const input = page.getByPlaceholder(/type a message/i)
    await expect(input).toBeVisible()
  })

  test("can type a message into the input", async ({ page }) => {
    await page.goto("/")
    const input = page.getByPlaceholder(/type a message/i)
    await input.fill("Hello Talon")
    await expect(input).toHaveValue("Hello Talon")
  })

  test("send button is visible", async ({ page }) => {
    await page.goto("/")
    const sendBtn = page.getByRole("button", { name: /send/i })
    await expect(sendBtn).toBeVisible()
  })

  test("chat and health tabs switch views", async ({ page }) => {
    await page.goto("/")
    const healthBtn = page.getByRole("button", { name: /health/i })
    await healthBtn.click()
    await expect(page.locator("text=Provider Status")).toBeVisible()

    const chatBtn = page.getByRole("button", { name: /chat/i })
    await chatBtn.click()
    const input = page.getByPlaceholder(/type a message/i)
    await expect(input).toBeVisible()
  })
})

test.describe("Health Dashboard", () => {
  test("health tab shows provider cards", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("button", { name: /health/i }).click()
    await expect(page.locator("text=Provider Status")).toBeVisible()
  })
})
