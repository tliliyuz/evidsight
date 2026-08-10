import { expect, test, type Page } from '@playwright/test'

/**
 * 纠偏 2「工作台」视觉验收用例。
 * 固定 1280×720、Chromium、device scale 1、本地字体、reduced-motion（playwright.config.ts）。
 * 视觉门禁：普通用户空态 / 有最近研究与知识库 / 有运行任务 三态 × 浅色/深色 六张截图。
 * 时钟冻结 + timezoneId 固定，保证相对时间与问候文案跨机器稳定。
 * 行为门禁（六项导航顺序、普通用户不显示管理入口、空态行动入口）由 app-shell.test.tsx
 * 与 workbench.test.tsx 覆盖，本文件只负责视觉基线。
 */

const FIXED_NOW = new Date('2026-08-08T14:32:00+08:00')

const USER = { id: 'u-1', username: 'linmo', role: 'user', status: 'active' }

type TaskFixture = {
  task_id: string
  topic: string
  status: 'running' | 'completed' | 'partially_completed'
  source_strategy: 'knowledge' | 'web' | 'hybrid'
  progress: number
  /** 相对 FIXED_NOW 的更新时刻，驱动「X 分钟前 / X 小时前」相对时间。 */
  agoMs: number
}

const RECENT_TASK: TaskFixture = {
  task_id: 't-running',
  topic: '全球企业级 AI Agent 平台竞争格局',
  status: 'running',
  source_strategy: 'hybrid',
  progress: 0.68,
  agoMs: 6 * 60_000,
}

function taskList(items: TaskFixture[]) {
  return {
    total: items.length,
    page: 1,
    page_size: 5,
    items: items.map((fixture) => ({
      task_id: fixture.task_id,
      topic: fixture.topic,
      status: fixture.status,
      task_type: 'comparison',
      source_strategy: fixture.source_strategy,
      progress: fixture.progress,
      total_sources: 12,
      total_evidence: 5,
      report_id:
        fixture.status === 'completed' || fixture.status === 'partially_completed'
          ? `report-${fixture.task_id}`
          : null,
      created_at: new Date(FIXED_NOW.getTime() - fixture.agoMs).toISOString(),
      completed_at:
        fixture.status === 'running'
          ? null
          : new Date(FIXED_NOW.getTime() - fixture.agoMs).toISOString(),
    })),
  }
}

const DATA_TASKS: TaskFixture[] = [
  {
    task_id: 't-1',
    topic: 'Q2 客户流失原因与产品机会分析',
    status: 'partially_completed',
    source_strategy: 'knowledge',
    progress: 0.85,
    agoMs: 6 * 60_000,
  },
  {
    task_id: 't-2',
    topic: '2026 数据基础设施趋势观察',
    status: 'completed',
    source_strategy: 'web',
    progress: 1,
    agoMs: 2 * 3_600_000,
  },
  {
    task_id: 't-3',
    topic: '企业级 AI Agent 平台对比研究',
    status: 'completed',
    source_strategy: 'hybrid',
    progress: 1,
    agoMs: 26 * 3_600_000,
  },
]

function kbList(items: { name: string; doc_count: number; agoMs: number }[]) {
  return {
    total: items.length,
    page: 1,
    page_size: 5,
    items: items.map((fixture, index) => ({
      uuid: `kb-${index + 1}`,
      name: fixture.name,
      description: null,
      owner: '550e8400-e29b-41d4-a716-446655440001',
      visibility: 'private',
      status: 'active',
      doc_count: fixture.doc_count,
      chunk_count: fixture.doc_count * 3,
      created_at: new Date(FIXED_NOW.getTime() - fixture.agoMs).toISOString(),
      updated_at: new Date(FIXED_NOW.getTime() - fixture.agoMs).toISOString(),
    })),
  }
}

const DATA_KB = [
  { name: '产品规划与路线图', doc_count: 216, agoMs: 2 * 3_600_000 },
  { name: '客户反馈与访谈', doc_count: 489, agoMs: 26 * 3_600_000 },
  { name: '行业与竞品资料', doc_count: 128, agoMs: 3 * 86_400_000 },
]

type WorkbenchScenario = {
  tasks: TaskFixture[]
  knowledge: { name: string; doc_count: number; agoMs: number }[]
}

async function setupWorkbench(
  page: Page,
  theme: 'light' | 'dark',
  scenario: WorkbenchScenario,
): Promise<void> {
  // 登录态：restore() 会调用 csrfHeaders()，必须先有 evidsight_csrf Cookie
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
  // 按查询参数区分：status=running → 运行集（Chip 计数 / 活动任务），其余 → 最近列表
  await page.route('**/api/v1/research/tasks**', (route) => {
    const url = route.request().url()
    const running = url.includes('status=running')
    const list = running
      ? taskList(scenario.tasks.filter((task) => task.status === 'running'))
      : taskList(scenario.tasks)
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(list) })
  })
  await page.route('**/api/v1/knowledge-bases**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(kbList(scenario.knowledge)),
    }),
  )
}

async function openWorkbench(page: Page): Promise<void> {
  await page.clock.setFixedTime(FIXED_NOW)
  await page.goto('/workbench')
  // restore() → refresh + me 完成后才会放行受保护路由
  await expect(page.getByRole('heading', { name: /下午好，linmo/ })).toBeVisible()
}

test.describe('工作台视觉验收', () => {
  test('普通用户空态 - 浅色', async ({ page }) => {
    await setupWorkbench(page, 'light', { tasks: [], knowledge: [] })
    await openWorkbench(page)

    await expect(page.getByRole('link', { name: '开始研究', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: '创建知识库', exact: true })).toBeVisible()
    // 进行中的研究卡片始终渲染，无运行任务时显示占位
    await expect(page.getByRole('link', { name: '开始研究 →' })).toBeVisible()
    // 顶部运行任务 Chip 常显占位
    await expect(page.getByRole('button', { name: '暂无任务进行' })).toBeVisible()
    await expect(page).toHaveScreenshot('workbench-empty-light.png')
  })

  test('普通用户空态 - 深色', async ({ page }) => {
    await setupWorkbench(page, 'dark', { tasks: [], knowledge: [] })
    await openWorkbench(page)

    await expect(page.getByRole('link', { name: '开始研究', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: '创建知识库', exact: true })).toBeVisible()
    // 进行中的研究卡片始终渲染，无运行任务时显示占位
    await expect(page.getByRole('link', { name: '开始研究 →' })).toBeVisible()
    // 顶部运行任务 Chip 常显占位
    await expect(page.getByRole('button', { name: '暂无任务进行' })).toBeVisible()
    await expect(page).toHaveScreenshot('workbench-empty-dark.png')
  })

  test('有最近研究和知识库 - 浅色', async ({ page }) => {
    await setupWorkbench(page, 'light', { tasks: DATA_TASKS, knowledge: DATA_KB })
    await openWorkbench(page)

    await expect(page.getByText('Q2 客户流失原因与产品机会分析')).toBeVisible()
    await expect(page.getByText('产品规划与路线图')).toBeVisible()
    await expect(page.getByText('216 个文档')).toBeVisible()
    await expect(page).toHaveScreenshot('workbench-data-light.png')
  })

  test('有最近研究和知识库 - 深色', async ({ page }) => {
    await setupWorkbench(page, 'dark', { tasks: DATA_TASKS, knowledge: DATA_KB })
    await openWorkbench(page)

    await expect(page.getByText('Q2 客户流失原因与产品机会分析')).toBeVisible()
    await expect(page.getByText('产品规划与路线图')).toBeVisible()
    await expect(page.getByText('216 个文档')).toBeVisible()
    await expect(page).toHaveScreenshot('workbench-data-dark.png')
  })

  test('有运行任务 - 浅色', async ({ page }) => {
    await setupWorkbench(page, 'light', { tasks: [RECENT_TASK, ...DATA_TASKS], knowledge: DATA_KB })
    await openWorkbench(page)

    // 顶部真实运行任务 Chip（常显）
    await expect(page.getByRole('button', { name: /1 项研究进行中/ })).toBeVisible()
    // 右栏活动任务 Inset Panel
    await expect(page.getByRole('link', { name: /进入研究现场/ })).toBeVisible()
    await expect(page).toHaveScreenshot('workbench-running-light.png')
  })

  test('有运行任务 - 深色', async ({ page }) => {
    await setupWorkbench(page, 'dark', { tasks: [RECENT_TASK, ...DATA_TASKS], knowledge: DATA_KB })
    await openWorkbench(page)

    await expect(page.getByRole('button', { name: /1 项研究进行中/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /进入研究现场/ })).toBeVisible()
    await expect(page).toHaveScreenshot('workbench-running-dark.png')
  })

  test('命令入口点击原位展开输入框 - 浅色', async ({ page }) => {
    await setupWorkbench(page, 'light', { tasks: [], knowledge: [] })
    await openWorkbench(page)

    await page.getByRole('button', { name: /搜索或执行指令/ }).click()
    await expect(page.getByRole('combobox', { name: '搜索命令' })).toBeFocused()
    // 空输入不弹出命令列表
    await expect(page.getByRole('listbox')).toHaveCount(0)
    await expect(page).toHaveScreenshot('command-palette-open-light.png')
  })

  test('命令入口点击原位展开输入框 - 深色', async ({ page }) => {
    await setupWorkbench(page, 'dark', { tasks: [], knowledge: [] })
    await openWorkbench(page)

    await page.getByRole('button', { name: /搜索或执行指令/ }).click()
    await expect(page.getByRole('combobox', { name: '搜索命令' })).toBeFocused()
    await expect(page.getByRole('listbox')).toHaveCount(0)
    await expect(page).toHaveScreenshot('command-palette-open-dark.png')
  })

  test('输入后弹出过滤命令列表 - 浅色', async ({ page }) => {
    await setupWorkbench(page, 'light', { tasks: [], knowledge: [] })
    await openWorkbench(page)

    await page.getByRole('button', { name: /搜索或执行指令/ }).click()
    await page.getByRole('combobox', { name: '搜索命令' }).fill('知识库')
    await expect(page.getByRole('listbox')).toBeVisible()
    await expect(page.getByRole('listbox').getByText('创建知识库')).toBeVisible()
    await expect(page).toHaveScreenshot('command-palette-search-light.png')
  })

  test('输入无匹配展示「无匹配命令」且不顶起输入框', async ({ page }) => {
    await setupWorkbench(page, 'light', { tasks: [], knowledge: [] })
    await openWorkbench(page)

    await page.getByRole('button', { name: /搜索或执行指令/ }).click()
    const input = page.getByRole('combobox', { name: '搜索命令' })
    const before = await input.boundingBox()

    await input.fill('不存在的命令xyz')
    await expect(page.getByText('无匹配命令')).toBeVisible()
    const after = await input.boundingBox()
    // 空态必须是绝对定位浮层，不得参与流内高度把输入框顶出顶栏
    expect(Math.round(after!.y)).toBe(Math.round(before!.y))
    await expect(page).toHaveScreenshot('command-palette-empty-light.png')
  })
})
