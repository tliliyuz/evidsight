import { expect, test } from '@playwright/test'

/**
 * 纠偏 1「入口页与登录抽屉」视觉验收用例。
 * 固定 1280×720、Chromium、device scale 1、本地字体、reduced-motion（playwright.config.ts）。
 * 视觉门禁：深色入口默认 / 登录抽屉打开 / 登录失败 / 提交中 四张截图，以及键盘焦点门禁。
 */
test.describe('入口页与登录抽屉视觉验收', () => {
  test('深色入口默认截图', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByRole('heading', { level: 1, name: /看见线索之间/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /进入据见/ })).toBeVisible()
    await expect(page).toHaveScreenshot('landing-default.png', { fullPage: true })
  })

  test('登录抽屉打开截图', async ({ page }) => {
    await page.goto('/login')

    const drawer = page.getByRole('dialog', { name: '登录据见' })
    await expect(drawer).toBeVisible()
    await expect(page.getByLabel('账号')).toBeFocused()
    await expect(page).toHaveScreenshot('login-drawer-open.png')
  })

  test('登录失败截图', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'E1001', message: '认证失败' }),
      }),
    )

    await page.goto('/login')
    await page.getByLabel('账号').fill('alice')
    await page.getByLabel('密码').fill('wrong-password')
    await page.getByRole('button', { name: '登录', exact: true }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    // 输入内容固定且字体已经本地化，账号、密码框与错误态必须完整进入视觉基线；
    // 禁止用 Playwright 默认洋红遮罩污染截图并绕过输入框视觉验收。
    await expect(page).toHaveScreenshot('login-drawer-error.png')
  })

  test('提交中截图', async ({ page }) => {
    await page.route('**/api/v1/auth/login', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 3000))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: 'x', token_type: 'bearer', expires_in: 3600 }),
      })
    })
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'u-1', username: 'alice', role: 'user', status: 'active' }),
      }),
    )

    await page.goto('/login')
    await page.getByLabel('账号').fill('alice')
    await page.getByLabel('密码').fill('password')
    await page.getByRole('button', { name: '登录', exact: true }).click()

    await expect(page.getByRole('button', { name: '正在登录…' })).toBeVisible()
    await expect(page).toHaveScreenshot('login-drawer-submitting.png')
  })

  test('键盘焦点顺序、Escape 和关闭后焦点恢复', async ({ page }) => {
    await page.goto('/')
    const loginLink = page.getByRole('link', { name: '登录' })
    await loginLink.click()

    // 打开后焦点进入首个有效控件
    await expect(page.getByLabel('账号')).toBeFocused()

    // Tab 顺序：账号 → 密码 → 显示 → 记住登录状态 → 提交
    await page.keyboard.press('Tab')
    await expect(page.getByLabel('密码')).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('button', { name: '显示' })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('checkbox', { name: /记住登录状态/ })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('button', { name: '登录', exact: true })).toBeFocused()

    // Escape 关闭非破坏性表面
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: '登录据见' })).not.toBeVisible()

    // 关闭后焦点返回触发器（登录入口）
    await expect(loginLink).toBeFocused()
  })
})
