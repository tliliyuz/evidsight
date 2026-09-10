import { expect, test, type Page } from '@playwright/test'

/**
 * 切片 4「问答历史」视觉验收用例。
 * 固定 1280×720、Chromium、device scale 1、本地字体、reduced-motion、Asia/Shanghai（playwright.config.ts）。
 * 覆盖：台账有数据、空态、查询失败、搜索（服务端 q）、排序、分页；浅色与深色各一套截图基线。
 * 行为门禁（删除回退页码、重命名/删除失败反馈等）由 chat-history-page.test.tsx 覆盖。
 */

const FIXED_NOW = new Date('2026-08-08T14:32:00+08:00')

const USER = { id: 'u-1', username: 'linmo', role: 'user', status: 'active' }

function iso(agoMs: number): string {
  return new Date(FIXED_NOW.getTime() - agoMs).toISOString()
}

function makeConversation(overrides: Partial<Record<string, unknown>>): Record<string, unknown> {
  return {
    uuid: `conv-${overrides.uuid ?? '1'}`,
    owner_user_id: 'u-1',
    kb_uuid: 'kb-1',
    kb_status: 'active',
    kb_name: '客户反馈与访谈',
    original_kb_uuid: null,
    original_kb_name: null,
    title: '企业级 Agent 采购标准',
    message_count: 8,
    created_at: iso(7 * 86_400_000),
    updated_at: iso(3_600_000),
    last_message_at: iso(3_600_000),
    ...overrides,
  }
}

const CONVERSATIONS = [
  makeConversation({
    uuid: '1',
    title: '企业级 Agent 采购标准',
    kb_name: '客户反馈与访谈',
    message_count: 8,
    last_message_at: iso(10 * 60_000),
  }),
  makeConversation({
    uuid: '2',
    title: 'Q2 流失客户共同信号',
    kb_name: '客户反馈与访谈',
    message_count: 14,
    last_message_at: iso(26 * 3_600_000),
  }),
  makeConversation({
    uuid: '3',
    title: '私有化部署风险',
    kb_name: '行业与竞品资料',
    message_count: 11,
    last_message_at: iso(8 * 86_400_000),
  }),
  makeConversation({
    uuid: '4',
    title: '权限继承与治理边界',
    kb_name: '安全与合规基线',
    message_count: 5,
    last_message_at: iso(12 * 86_400_000),
  }),
  makeConversation({
    uuid: '5',
    title: '检索增强与证据可追溯',
    kb_name: '产品规划与路线图',
    message_count: 9,
    last_message_at: iso(20 * 86_400_000),
  }),
]

type SetupOptions = {
  theme: 'light' | 'dark'
  items?: Record<string, unknown>[]
  total?: number
  listError?: boolean
  /** 服务端搜索：仅标题匹配，模拟真实 q 语义。 */
  searchable?: boolean
}

async function setupHistory(
  page: Page,
  { theme, items, total, listError, searchable }: SetupOptions,
): Promise<void> {
  await page.addInitScript(() => {
    document.cookie = 'evidsight_csrf=e2e-csrf; path=/'
  })
  if (theme === 'dark') {
    await page.addInitScript(() => localStorage.setItem('evidsight-theme', 'dark'))
  }

  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: 'e2e-token', token_type: 'bearer', expires_in: 3600 }),
    }),
  )
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(USER) }),
  )
  await page.route('**/api/v1/research/tasks**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total: 0, page: 1, page_size: 1, items: [] }),
    }),
  )

  const all = items ?? CONVERSATIONS
  await page.route('**/api/v1/conversations**', (route) => {
    const url = new URL(route.request().url())
    // 列表（GET /api/v1/conversations）走服务端搜索/排序/分页语义；其余（详情/重命名/删除）不涉及本页视觉
    if (route.request().method() === 'GET' && url.pathname === '/api/v1/conversations') {
      if (listError) {
        route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
        return
      }
      const keyword = (url.searchParams.get('q') ?? '').trim()
      let shown = all
      if (searchable && keyword) {
        shown = all.filter((c) => String(c.title).includes(keyword))
      }
      const pageNo = Number(url.searchParams.get('page') ?? '1')
      const pageSize = Number(url.searchParams.get('page_size') ?? '10')
      const slice = shown.slice((pageNo - 1) * pageSize, pageNo * pageSize)
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total: total ?? shown.length,
          page: pageNo,
          page_size: pageSize,
          items: slice,
        }),
      })
      return
    }
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
}

async function openHistory(page: Page, query = ''): Promise<void> {
  await page.clock.setFixedTime(FIXED_NOW)
  await page.goto(`/chat/history${query}`)
  await expect(page.getByRole('heading', { name: '问答历史', exact: true })).toBeVisible()
}

test.describe('问答历史视觉验收', () => {
  test('台账有数据 - 浅色', async ({ page }) => {
    await setupHistory(page, { theme: 'light' })
    await openHistory(page)

    await expect(page.getByText('企业级 Agent 采购标准')).toBeVisible()
    await expect(page.getByText('Q2 流失客户共同信号')).toBeVisible()
    await expect(page.getByText('客户反馈与访谈').first()).toBeVisible()
    await expect(page.getByText('8 条消息').first()).toBeVisible()
    await expect(page.getByRole('link', { name: '新建对话' })).toBeVisible()
    // 重命名/删除收敛到行内 ⋮ 溢出菜单，行内只保留「打开对话」主操作
    await expect(page.getByRole('button', { name: /会话操作/ }).first()).toBeVisible()
    await expect(page).toHaveScreenshot('history-ledger-light.png')
  })

  test('台账有数据 - 深色', async ({ page }) => {
    await setupHistory(page, { theme: 'dark' })
    await openHistory(page)

    await expect(page.getByText('企业级 Agent 采购标准')).toBeVisible()
    await expect(page).toHaveScreenshot('history-ledger-dark.png')
  })

  test('空态 - 浅色', async ({ page }) => {
    await setupHistory(page, { theme: 'light', items: [] })
    await openHistory(page)

    await expect(page.getByText('还没有问答历史')).toBeVisible()
    await expect(page.getByRole('link', { name: '开始问答' })).toBeVisible()
    await expect(page).toHaveScreenshot('history-empty-light.png')
  })

  test('查询失败 - 浅色', async ({ page }) => {
    await setupHistory(page, { theme: 'light', listError: true })
    await openHistory(page)

    await expect(page.getByText('暂时无法加载')).toBeVisible()
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible()
    await expect(page).toHaveScreenshot('history-error-light.png')
  })

  test('搜索（服务端仅标题匹配）- 浅色', async ({ page }) => {
    await setupHistory(page, { theme: 'light', searchable: true })
    await openHistory(page)

    await page.getByPlaceholder('搜索会话名称').fill('Q2')
    await expect(page.getByText('Q2 流失客户共同信号')).toBeVisible()
    await expect(page.getByText('企业级 Agent 采购标准')).toHaveCount(0)
    await expect(page).toHaveScreenshot('history-search-light.png')
  })

  test('排序切换 - 浅色', async ({ page }) => {
    await setupHistory(page, { theme: 'light' })
    await openHistory(page)

    await page.getByRole('button', { name: /更新时间/ }).click()
    await expect(page.getByRole('button', { name: /更新时间 ↑/ })).toBeVisible()
    await expect(page).toHaveScreenshot('history-sort-asc-light.png')
  })

  test('分页（总数 25 → 3 页）- 浅色', async ({ page }) => {
    const many = Array.from({ length: 12 }, (_, i) =>
      makeConversation({
        uuid: String(i + 1),
        title: `历史会话 ${i + 1}`,
        message_count: 2 + i,
        last_message_at: iso((i + 1) * 3_600_000),
      }),
    )
    await setupHistory(page, { theme: 'light', items: many, total: 25 })
    await openHistory(page)

    await expect(page.getByText(/第 1 \/ 3 页/)).toBeVisible()
    await expect(page.getByRole('button', { name: '下一页' })).toBeVisible()
    await expect(page).toHaveScreenshot('history-pagination-light.png')
  })
})
