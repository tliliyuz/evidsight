import { expect, test, type Page } from '@playwright/test'

/**
 * 切片 4「据见问答」视觉验收用例。
 * 固定 1280×720、Chromium、device scale 1、本地字体、reduced-motion、Asia/Shanghai（playwright.config.ts）。
 * 覆盖：空会话（无 KB）、已有问答（真实标题/角色符/引用条/来源卡）、流式生成、KB 选择器打开态、
 * 来源详情抽屉 → 切片抽屉、权限撤销（403）受限态，浅色与深色各一套截图基线。
 * 时钟冻结 + timezoneId 固定，保证相对时间跨机器稳定。
 * 行为门禁（isComposing、自动滚动、停止按钮等）由 chat-page.test.tsx / chat-generation-machine.test.ts 覆盖。
 */

const FIXED_NOW = new Date('2026-08-08T14:32:00+08:00')

const USER = { id: 'u-1', username: 'linmo', role: 'user', status: 'active' }

const KB = {
  uuid: 'kb-1',
  name: '客户反馈与访谈',
  description: '访谈纪要、工单摘录与续约复盘',
  owner: 'u-1',
  visibility: 'private',
  status: 'active',
  doc_count: 489,
  chunk_count: 3210,
  index_status: 'ready',
  owner_username: 'linmo',
  created_at: new Date(FIXED_NOW.getTime() - 60 * 86_400_000).toISOString(),
  updated_at: new Date(FIXED_NOW.getTime() - 26 * 3_600_000).toISOString(),
}

const SOURCES = [
  {
    chunk_index: 1,
    document_uuid: 'doc-1',
    segment_id: 'seg-1',
    doc_name: '企业 AI 平台采购复盘（Q2）',
    score: 0.92,
    page: 18,
    section_title: '采购标准',
    section_path: '复盘 / 采购标准',
    preview_text: '权限体系能否原样继承，是进入试点前必须完成的验证。',
    highlight_start: 0,
    highlight_end: 4,
  },
  {
    chunk_index: 2,
    document_uuid: 'doc-1',
    segment_id: 'seg-2',
    doc_name: '权限治理基线',
    score: 0.71,
    page: 3,
    section_title: '治理边界',
    section_path: '基线 / 治理边界',
    preview_text: '高风险工具应具备审批、审计与可撤销能力。',
    highlight_start: null,
    highlight_end: null,
  },
]

const CONVERSATION = {
  uuid: 'conv-1',
  owner_user_id: 'u-1',
  kb_uuid: 'kb-1',
  kb_status: 'active',
  kb_name: '客户反馈与访谈',
  original_kb_uuid: null,
  original_kb_name: null,
  title: '企业级 Agent 采购标准',
  message_count: 2,
  created_at: new Date(FIXED_NOW.getTime() - 7 * 86_400_000).toISOString(),
  updated_at: new Date(FIXED_NOW.getTime() - 1 * 3_600_000).toISOString(),
  last_message_at: new Date(FIXED_NOW.getTime() - 1 * 3_600_000).toISOString(),
  messages: [
    {
      id: 1,
      role: 'user',
      content: '客户在试点 Agent 时最先验证什么？',
      created_at: new Date(FIXED_NOW.getTime() - 1 * 3_600_000).toISOString(),
    },
    {
      id: 2,
      role: 'assistant',
      content:
        '从当前材料看，客户最先验证的是权限继承、工具执行的治理边界，以及结果能否回溯到原始材料。',
      created_at: new Date(FIXED_NOW.getTime() - 1 * 3_600_000).toISOString(),
      sources: SOURCES,
    },
  ],
}

const SSE_FULL = [
  'event: meta',
  'id: 1',
  'data: ' + JSON.stringify({ conversation_id: 'conv-1', generation_id: 'gen-1' }),
  '',
  'event: message.delta',
  'id: 2',
  'data: ' + JSON.stringify({ delta: '权限体系需要原样继承' }),
  '',
  'event: message.delta',
  'id: 3',
  'data: ' + JSON.stringify({ delta: '，并在每次检索时复核。' }),
  '',
  'event: sources',
  'id: 4',
  'data: ' +
    JSON.stringify({ chunks: SOURCES, confidence: '高', confidence_note: '基于 2 个来源' }),
  '',
  'event: done',
  'id: 5',
  'data: ' + JSON.stringify({ message_id: 2, title: '企业级 Agent 采购标准' }),
  '',
].join('\n')

type SetupOptions = {
  theme: 'light' | 'dark'
  conversation?: unknown
  kbList?: unknown[]
  streamBody?: string
  /** location 返回 403（受限态截图）。 */
  locationRestricted?: boolean
}

async function setupChat(
  page: Page,
  { theme, conversation, kbList, streamBody, locationRestricted }: SetupOptions,
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
  await page.route('**/api/v1/knowledge-bases**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total: (kbList ?? [KB]).length,
        page: 1,
        page_size: 20,
        items: kbList ?? [KB],
      }),
    }),
  )
  await page.route('**/api/v1/conversations/*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(conversation ?? CONVERSATION),
    }),
  )
  if (streamBody !== undefined) {
    await page.route('**/api/v1/chat/stream', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: { 'cache-control': 'no-cache' },
        body: streamBody,
      }),
    )
  }
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
            segment_id: 'seg-1',
            chunk_index: 0,
            preview: '权限继承：进入试点前必须完成的验证',
            token_count: 128,
            metadata: { page: 18 },
          },
          {
            id: 2,
            segment_id: 'seg-2',
            chunk_index: 1,
            preview: '治理边界：高风险工具审批与撤销',
            token_count: 96,
            metadata: { page: 3 },
          },
        ],
      }),
    }),
  )
  await page.route('**/api/v1/documents/doc-1/locations/**', (route) => {
    if (locationRestricted) {
      route.fulfill({ status: 403, contentType: 'application/json', body: '{}' })
      return
    }
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        document_id: 'doc-1',
        segment_id: 'seg-1',
        minimal_excerpt: '权限体系能否原样继承，是进入试点前必须完成的验证。',
        location: { page_number: 18 },
        source_updated_at: new Date(FIXED_NOW.getTime() - 2 * 3_600_000).toISOString(),
      }),
    })
  })
}

async function openChat(page: Page, query = ''): Promise<void> {
  await page.clock.setFixedTime(FIXED_NOW)
  await page.goto(`/chat${query}`)
  await expect(
    page.getByRole('heading', { name: /据见问答|新对话|企业级 Agent 采购标准/ }),
  ).toBeVisible()
}

test.describe('据见问答视觉验收', () => {
  test('空会话（未选知识库）- 浅色', async ({ page }) => {
    await setupChat(page, { theme: 'light' })
    await openChat(page)

    await expect(page.getByText('请先选择知识库，再开始问答。')).toBeVisible()
    await expect(page.getByRole('button', { name: '发送' })).toBeDisabled()
    await expect(page).toHaveScreenshot('chat-empty-light.png')
  })

  test('空会话（未选知识库）- 深色', async ({ page }) => {
    await setupChat(page, { theme: 'dark' })
    await openChat(page)

    await expect(page.getByText('请先选择知识库，再开始问答。')).toBeVisible()
    await expect(page).toHaveScreenshot('chat-empty-dark.png')
  })

  test('已有问答：真实标题、角色符、引用条 - 浅色', async ({ page }) => {
    await setupChat(page, { theme: 'light' })
    await openChat(page, '?conversation=conv-1')

    await expect(page.getByRole('heading', { name: '企业级 Agent 采购标准' })).toBeVisible()
    await expect(page.getByText(/你 · \d{2}:\d{2}/)).toBeVisible()
    await expect(page.getByText(/EvidSight · \d{2}:\d{2}/)).toBeVisible()
    // 来源以引用锚点呈现（点击序号打开来源详情抽屉），不在页面平铺
    await expect(page.getByRole('button', { name: '引用来源 1' })).toBeVisible()
    await expect(page.getByText('企业 AI 平台采购复盘（Q2）')).toHaveCount(0)
    await expect(page).toHaveScreenshot('chat-history-light.png')
  })

  test('已有问答：真实标题、角色符、引用条 - 深色', async ({ page }) => {
    await setupChat(page, { theme: 'dark' })
    await openChat(page, '?conversation=conv-1')

    await expect(page.getByRole('heading', { name: '企业级 Agent 采购标准' })).toBeVisible()
    await expect(page.getByRole('button', { name: '引用来源 1' })).toBeVisible()
    await expect(page).toHaveScreenshot('chat-history-dark.png')
  })

  test('流式生成：发送后展示回答并进入成功终态 - 浅色', async ({ page }) => {
    await setupChat(page, { theme: 'light', streamBody: SSE_FULL })
    await openChat(page)

    await page.getByRole('button', { name: /已选知识库/ }).click()
    await page.getByRole('option', { name: /客户反馈与访谈/ }).click()
    await page.getByLabel('输入问题').fill('客户在试点 Agent 时最先验证什么？')
    await page.getByRole('button', { name: '发送' }).click()

    // 流式 delta 落屏，来源条出现，最终进入成功终态（不再显示「生成中」）
    await expect(page.getByText(/权限体系需要原样继承/)).toBeVisible()
    await expect(page.getByRole('button', { name: '引用来源 1' })).toBeVisible()
    await expect(page.getByText(/使用 1 个知识库 · 2 个来源/)).toBeVisible()
    await expect(page.getByText('生成中')).toHaveCount(0)
    await expect(page).toHaveScreenshot('chat-streaming-done-light.png')
  })

  test('来源详情抽屉 → 切片抽屉（实时鉴权）- 浅色', async ({ page }) => {
    await setupChat(page, { theme: 'light' })
    await openChat(page, '?conversation=conv-1')

    await page.getByRole('button', { name: '引用来源 1' }).click()
    const drawer = page.getByRole('dialog', { name: '回答依据' })
    await expect(drawer).toBeVisible()
    await expect(drawer.getByText('客户反馈与访谈')).toBeVisible()
    await expect(page).toHaveScreenshot('chat-source-detail-light.png')

    await page.getByRole('button', { name: '进入文档切片' }).click()
    const slice = page.getByRole('dialog', { name: '文档切片' })
    await expect(slice).toBeVisible()
    await expect(
      slice.getByText('权限体系能否原样继承，是进入试点前必须完成的验证。'),
    ).toBeVisible()
    await expect(page).toHaveScreenshot('chat-slice-drawer-light.png')
  })

  test('权限撤销（403）：切片受限态保留元数据 - 浅色', async ({ page }) => {
    await setupChat(page, { theme: 'light', locationRestricted: true })
    await openChat(page, '?conversation=conv-1')

    await page.getByRole('button', { name: '引用来源 1' }).click()
    await page.getByRole('button', { name: '进入文档切片' }).click()
    await expect(page.getByRole('dialog', { name: '文档切片' })).toBeVisible()
    await expect(page.getByText('原文已不可访问')).toBeVisible()
    await expect(page.getByText(/你的访问权限已被撤销/)).toBeVisible()
    await expect(page).toHaveScreenshot('chat-slice-restricted-light.png')
  })

  test('知识库选择器打开态 - 浅色', async ({ page }) => {
    await setupChat(page, { theme: 'light' })
    await openChat(page)

    await page.getByRole('button', { name: /已选知识库/ }).click()
    await expect(page.getByRole('combobox')).toBeFocused()
    await expect(page.getByRole('option', { name: /客户反馈与访谈/ })).toBeVisible()
    await expect(page).toHaveScreenshot('chat-kb-picker-light.png')
  })

  test('页头「重命名」与「已选知识库」数量徽章 + scope-summary - 浅色', async ({ page }) => {
    await setupChat(page, { theme: 'light' })
    await openChat(page, '?conversation=conv-1')

    // 已选知识库数量徽章（v1 单选为 1）
    await expect(page.getByRole('button', { name: /已选知识库 1/ })).toBeVisible()
    // 重命名按钮
    await expect(page.getByRole('button', { name: '重命名' })).toBeVisible()
    // scope-summary 展示会话知识库名称
    await expect(page.getByText(/本对话已选择「客户反馈与访谈」/)).toBeVisible()
    // 回答底部信息栏：知识库 + 来源数量 + 复制回答
    await expect(page.getByText(/使用 1 个知识库 · 2 个来源/)).toBeVisible()
    await expect(page.getByRole('button', { name: '复制回答' })).toBeVisible()
    await expect(page).toHaveScreenshot('chat-header-scope-light.png')
  })
})
