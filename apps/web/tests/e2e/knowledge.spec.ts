import { expect, test, type Page } from '@playwright/test'

/**
 * 纠偏 3B「知识中心」视觉验收用例。
 * 固定 1280×720、Chromium、device scale 1、本地字体、reduced-motion、Asia/Shanghai（playwright.config.ts）。
 * 视觉门禁：列表（有数据/空态/错误/分页）、详情六种文档状态、Drawer（创建/上传/切片/权限撤销）、
 * 权限（owner/只读成员/admin 非 owner）浅色与深色各一套截图基线。
 * 时钟冻结 + timezoneId 固定，保证相对时间跨机器稳定。
 * 行为门禁（权限按钮、状态筛选、具名删除确认、六值映射）由 knowledge-list/detail/chunk-drawer.test.tsx 覆盖。
 */

const FIXED_NOW = new Date('2026-08-08T14:32:00+08:00')

const KB_OWNER = '550e8400-e29b-41d4-a716-446655440001'
const OTHER_USER_ID = '550e8400-e29b-41d4-a716-446655440099'

const OWNER_USER = { id: KB_OWNER, username: 'linmo', role: 'user', status: 'active' }
const READONLY_USER = { id: OTHER_USER_ID, username: 'guest', role: 'user', status: 'active' }
const ADMIN_USER = {
  id: '550e8400-e29b-41d4-a716-446655440098',
  username: 'admin',
  role: 'admin',
  status: 'active',
}

function iso(agoMs: number): string {
  return new Date(FIXED_NOW.getTime() - agoMs).toISOString()
}

const KB_LIST = {
  total: 4,
  page: 1,
  page_size: 20,
  items: [
    {
      uuid: 'kb-1',
      name: '产品规划与路线图',
      description: '战略、季度规划与关键决策记录',
      owner: KB_OWNER,
      visibility: 'private',
      status: 'active',
      doc_count: 216,
      chunk_count: 18420,
      index_status: 'ready',
      owner_username: 'linmo',
      created_at: iso(30 * 86_400_000),
      updated_at: iso(2 * 3_600_000),
    },
    {
      uuid: 'kb-2',
      name: '客户反馈与访谈',
      description: '访谈纪要、工单摘录与续约复盘',
      owner: KB_OWNER,
      visibility: 'private',
      status: 'active',
      doc_count: 489,
      chunk_count: 3210,
      index_status: 'updating',
      owner_username: 'linmo',
      created_at: iso(60 * 86_400_000),
      updated_at: iso(26 * 3_600_000),
    },
    {
      uuid: 'kb-3',
      name: '行业与竞品资料',
      description: '公开产品资料与内部竞争情报',
      owner: KB_OWNER,
      visibility: 'public',
      status: 'active',
      doc_count: 128,
      chunk_count: 964,
      index_status: 'ready',
      owner_username: 'linmo',
      created_at: iso(90 * 86_400_000),
      updated_at: iso(3 * 86_400_000),
    },
    {
      uuid: 'kb-4',
      name: '安全与合规基线',
      description: '组织公开的制度、基线与审计手册',
      owner: KB_OWNER,
      visibility: 'public',
      status: 'active',
      doc_count: 84,
      chunk_count: 520,
      index_status: 'recovering',
      owner_username: 'linmo',
      created_at: iso(120 * 86_400_000),
      updated_at: iso(5 * 86_400_000),
    },
  ],
}

const SIX_DOCS = [
  {
    uuid: 'doc-1',
    kb_uuid: 'kb-1',
    filename: '2026_H2_Product_Roadmap.pdf',
    file_type: 'pdf',
    file_size: 13_421_773,
    status: 'completed',
    chunk_count: 1284,
    error_msg: null,
    created_at: iso(2 * 3_600_000),
    updated_at: iso(2 * 3_600_000),
  },
  {
    uuid: 'doc-2',
    kb_uuid: 'kb-1',
    filename: 'Agent_Platform_Strategy.docx',
    file_type: 'docx',
    file_size: 4_403_200,
    status: 'processing',
    chunk_count: 0,
    error_msg: null,
    created_at: iso(4 * 3_600_000),
    updated_at: iso(4 * 3_600_000),
  },
  {
    uuid: 'doc-3',
    kb_uuid: 'kb-1',
    filename: 'Q3_Planning_Notes.md',
    file_type: 'md',
    file_size: 696_320,
    status: 'queued',
    chunk_count: 0,
    error_msg: null,
    created_at: iso(6 * 3_600_000),
    updated_at: iso(6 * 3_600_000),
  },
  {
    uuid: 'doc-4',
    kb_uuid: 'kb-1',
    filename: 'Product_Decisions_Archive.pdf',
    file_type: 'pdf',
    file_size: 29_783_654,
    status: 'partial',
    chunk_count: 2109,
    error_msg: '第 46–48 页图像无法提取',
    created_at: iso(26 * 3_600_000),
    updated_at: iso(26 * 3_600_000),
  },
  {
    uuid: 'doc-5',
    kb_uuid: 'kb-1',
    filename: 'Legacy_Feature_Matrix.pdf',
    file_type: 'pdf',
    file_size: 10_066_330,
    status: 'failed',
    chunk_count: 0,
    error_msg: '文件已加密，无法解析内容',
    created_at: iso(26 * 3_600_000),
    updated_at: iso(26 * 3_600_000),
  },
  {
    uuid: 'doc-6',
    kb_uuid: 'kb-1',
    filename: 'Old_Archive_Notes.txt',
    file_type: 'txt',
    file_size: 12_800,
    status: 'deleting',
    chunk_count: 0,
    error_msg: null,
    created_at: iso(3 * 86_400_000),
    updated_at: iso(3 * 86_400_000),
  },
]

const SEGMENT_1 = '550e8400-e29b-41d4-a716-446655440301'
const SEGMENT_2 = '550e8400-e29b-41d4-a716-446655440302'

type SetupOptions = {
  theme: 'light' | 'dark'
  user: typeof OWNER_USER | typeof READONLY_USER | typeof ADMIN_USER
  kbList?: unknown[]
  kbDetail?: unknown
  docs?: unknown[]
  /** 列表接口返回 500（错误态截图）。 */
  listError?: boolean
  /** 分页态：让列表总数超过一页，且当前请求返回第 N 页数据。 */
  kbPage?: { page: number; total: number }
}

const KB_DETAIL = {
  uuid: 'kb-1',
  name: '产品规划与路线图',
  description: '战略、季度规划与关键决策记录',
  owner: KB_OWNER,
  visibility: 'private',
  status: 'active',
  doc_count: 6,
  chunk_count: 1284,
  index_status: 'ready',
  owner_username: 'linmo',
  created_at: iso(30 * 86_400_000),
  updated_at: iso(2 * 3_600_000),
}

async function setupKnowledge(
  page: Page,
  { theme, user, kbList: listOverride, kbDetail, docs, listError, kbPage }: SetupOptions,
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
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(user) }),
  )
  // AppShell 运行任务 Chip 常驻请求：返回空运行集，保持「暂无任务进行」确定性，避免打到真实后端
  await page.route('**/api/v1/research/tasks**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total: 0, page: 1, page_size: 1, items: [] }),
    }),
  )

  // 统一处理 knowledge-bases 前缀：列表 / 详情 / 文档列表（chunks/locations 在 /documents 前缀单独注册）
  await page.route('**/api/v1/knowledge-bases**', (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/v1/knowledge-bases') {
      if (listError) {
        route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
        return
      }
      const url = new URL(route.request().url())
      const pageNo = Number(url.searchParams.get('page') ?? '1')
      const total = kbPage?.total ?? KB_LIST.total
      const items = listOverride ?? KB_LIST.items
      // 分页态：请求页返回对应数据，其余页返回空，仅验证分页控件与「第 N / M 页」渲染
      const shown = kbPage ? (pageNo === kbPage.page ? items : []) : items
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total, page: pageNo, page_size: 20, items: shown }),
      })
      return
    }
    if (pathname.endsWith('/documents')) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total: (docs ?? SIX_DOCS).length,
          page: 1,
          page_size: 20,
          items: docs ?? SIX_DOCS,
        }),
      })
      return
    }
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(kbDetail ?? KB_DETAIL),
    })
  })

  await page.route('**/api/v1/documents/doc-1/chunks**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total: 2,
        page: 1,
        page_size: 50,
        items: [
          {
            id: 1,
            segment_id: SEGMENT_1,
            chunk_index: 0,
            preview: '第一段安全预览：产品路线图 H2 目标',
            token_count: 128,
            metadata: { page: 3 },
          },
          {
            id: 2,
            segment_id: SEGMENT_2,
            chunk_index: 1,
            preview: '第二段安全预览：关键里程碑',
            token_count: 96,
            metadata: { page: 4 },
          },
        ],
      }),
    }),
  )
  await page.route('**/api/v1/documents/doc-1/locations/**', (route) => {
    const locationId = new URL(route.request().url()).pathname.split('/').pop()
    if (locationId === SEGMENT_2) {
      route.fulfill({ status: 403, contentType: 'application/json', body: '{}' })
      return
    }
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        document_id: 'doc-1',
        segment_id: SEGMENT_1,
        minimal_excerpt: '2026 H2 聚焦企业级 Agent 平台，重点投入检索增强与证据可追溯。',
        location: { page_number: 3 },
        source_updated_at: iso(2 * 3_600_000),
      }),
    })
  })
}

async function openList(page: Page): Promise<void> {
  await page.clock.setFixedTime(FIXED_NOW)
  await page.goto('/knowledge-bases')
  await expect(page.getByRole('heading', { name: '知识库', exact: true })).toBeVisible()
}

async function openDetail(page: Page): Promise<void> {
  await page.clock.setFixedTime(FIXED_NOW)
  await page.goto('/knowledge-bases/kb-1')
  await expect(page.getByRole('heading', { name: '产品规划与路线图' })).toBeVisible()
}

test.describe('知识中心视觉验收', () => {
  test('列表有数据 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER })
    await openList(page)

    await expect(page.getByText('产品规划与路线图')).toBeVisible()
    await expect(page.getByText('可检索').first()).toBeVisible()
    await expect(page.getByText('索引更新中')).toBeVisible()
    await expect(page.getByText('恢复中')).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-list-light.png')
  })

  test('列表有数据 - 深色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'dark', user: OWNER_USER })
    await openList(page)

    await expect(page.getByText('产品规划与路线图')).toBeVisible()
    await expect(page.getByText('索引更新中')).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-list-dark.png')
  })

  test('列表空态 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER, kbList: [] })
    await openList(page)

    await expect(page.getByText('还没有知识库')).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-list-empty-light.png')
  })

  test('列表加载失败 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER, listError: true })
    await openList(page)

    await expect(page.getByText('暂时无法加载')).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-list-error-light.png')
  })

  test('列表分页 - 浅色（总数超过一页，默认 10 条/页）', async ({ page }) => {
    await setupKnowledge(page, {
      theme: 'light',
      user: OWNER_USER,
      kbPage: { page: 1, total: 25 },
    })
    await openList(page)

    // page_size=10 → 25 条共 3 页，展示页码按钮与「第 1 / 3 页」
    await expect(page.getByText(/第 1 \/ 3 页/)).toBeVisible()
    await expect(page.getByRole('button', { name: '下一页' })).toBeVisible()
    await expect(page.getByRole('button', { name: '2' })).toBeVisible()
    await expect(page.getByRole('button', { name: '3' })).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-list-pagination-light.png')
  })

  test('三个真实 Scope - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER })
    await openList(page)

    await expect(page.getByRole('button', { name: '全部' })).toBeVisible()
    await expect(page.getByRole('button', { name: '我创建的' })).toBeVisible()
    await expect(page.getByRole('button', { name: '组织公开' })).toBeVisible()

    await page.getByRole('button', { name: '我创建的' }).click()
    // 只读成员与 owner 场景下，切换到 mine 后请求携带 scope=mine
    await expect(page).toHaveScreenshot('knowledge-list-scope-mine-light.png')
  })

  test('详情六种文档状态 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER })
    await openDetail(page)

    // 状态文案限定在文档 Ledger 内断言（状态筛选下拉含相同文案，避免严格模式歧义）
    const docLedger = page.getByRole('list')
    await expect(page.getByText('2026_H2_Product_Roadmap.pdf')).toBeVisible()
    await expect(docLedger.getByText('处理失败')).toBeVisible()
    await expect(docLedger.getByText('文件已加密，无法解析内容')).toBeVisible()
    await expect(docLedger.getByText('部分可用')).toBeVisible()
    await expect(docLedger.getByText('删除中')).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-detail-light.png')
  })

  test('详情六种文档状态 - 深色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'dark', user: OWNER_USER })
    await openDetail(page)

    const docLedger = page.getByRole('list')
    await expect(page.getByText('2026_H2_Product_Roadmap.pdf')).toBeVisible()
    await expect(docLedger.getByText('处理失败')).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-detail-dark.png')
  })

  test('Drawer 创建知识库 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER })
    await openList(page)

    await page.getByRole('button', { name: '新建知识库' }).click()
    await expect(page.getByRole('dialog', { name: '新建知识库' })).toBeVisible()
    await expect(page.getByRole('textbox', { name: '知识库名称' })).toBeFocused()
    await expect(page).toHaveScreenshot('knowledge-drawer-create-light.png')
  })

  test('Drawer 上传文档 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER })
    await openDetail(page)

    await page.getByRole('button', { name: '上传文档' }).click()
    await expect(page.getByRole('dialog', { name: '上传文档' })).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-drawer-upload-light.png')
  })

  test('Drawer 切片与原文 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER })
    await openDetail(page)

    await page.getByRole('button', { name: '查看切片' }).first().click()
    await expect(page.getByRole('dialog', { name: '文档切片' })).toBeVisible()
    await expect(page.getByText('第一段安全预览：产品路线图 H2 目标')).toBeVisible()
    await page.getByRole('button', { name: '展开第一段' }).click()
    await expect(page.getByText(/2026 H2 聚焦企业级 Agent 平台/)).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-drawer-slice-light.png')
  })

  test('权限撤销（403）切片受限态 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: OWNER_USER })
    await openDetail(page)

    await page.getByRole('button', { name: '查看切片' }).first().click()
    await expect(page.getByRole('dialog', { name: '文档切片' })).toBeVisible()
    // 第二段 location 返回 403 → 立即清正文并展示受限态
    await page.getByRole('button', { name: '展开第二段' }).click()
    await expect(page.getByText('原文已不可访问')).toBeVisible()
    await expect(page).toHaveScreenshot('knowledge-drawer-slice-restricted-light.png')
  })

  test('权限：只读成员列表不显示编辑/删除 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: READONLY_USER })
    await openList(page)

    await expect(page.getByText('产品规划与路线图')).toBeVisible()
    await expect(page.getByRole('button', { name: '编辑' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '删除知识库' })).toHaveCount(0)
    await expect(page).toHaveScreenshot('knowledge-perm-readonly-light.png')
  })

  test('权限：管理员非 owner 治理可见编辑/删除 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: ADMIN_USER })
    // 编辑/删除知识库在详情页 Hero（列表操作列只保留主操作「进入知识库」）
    await openDetail(page)

    await expect(page.getByText('产品规划与路线图')).toBeVisible()
    // 治理权限在详情 Hero：admin 非 owner 可见编辑/删除，但上传为 owner-only，不可见
    await expect(page.getByRole('button', { name: '编辑' })).toBeVisible()
    await expect(page.getByRole('button', { name: '删除知识库' })).toBeVisible()
    await expect(page.getByRole('button', { name: '上传文档' })).toHaveCount(0)
    await expect(page).toHaveScreenshot('knowledge-perm-admin-governance-light.png')
  })

  test('权限：管理员非 owner 详情不显示上传入口 - 浅色', async ({ page }) => {
    await setupKnowledge(page, { theme: 'light', user: ADMIN_USER })
    await openDetail(page)

    await expect(page.getByRole('button', { name: '上传文档' })).toHaveCount(0)
    await expect(page).toHaveScreenshot('knowledge-perm-admin-detail-light.png')
  })
})
