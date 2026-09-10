import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserSummary } from '@/api/auth'
import { ToastProvider } from '@/components/feedback/ToastProvider'
import { KnowledgeBaseListPage } from '@/features/knowledge/KnowledgeBaseListPage'
import { formatTimestamp } from '@/features/knowledge/format'
import type { KnowledgeApi, KnowledgeBase } from '@/api/knowledge'

const KB_UUID = '550e8400-e29b-41d4-a716-446655440100'
const OWNER_ID = '550e8400-e29b-41d4-a716-446655440001'

const OWNER: UserSummary = { id: OWNER_ID, username: 'linmo', role: 'user', status: 'active' }
const READONLY_MEMBER: UserSummary = {
  id: '550e8400-e29b-41d4-a716-446655440099',
  username: 'other',
  role: 'user',
  status: 'active',
}
const ADMIN_NON_OWNER: UserSummary = {
  id: '550e8400-e29b-41d4-a716-446655440098',
  username: 'admin',
  role: 'admin',
  status: 'active',
}

function kb(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    uuid: KB_UUID,
    name: '合规资料',
    description: '内部合规制度',
    owner: OWNER_ID,
    visibility: 'private',
    status: 'active',
    doc_count: 2,
    chunk_count: 18,
    index_status: 'ready',
    owner_username: 'linmo',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-08T00:00:00Z',
    ...overrides,
  }
}

function makeApi(overrides: Partial<KnowledgeApi> = {}): KnowledgeApi {
  return {
    listKnowledgeBases: vi.fn().mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [kb()],
    }),
    createKnowledgeBase: vi.fn().mockResolvedValue(kb()),
    getKnowledgeBase: vi.fn().mockResolvedValue(kb()),
    updateKnowledgeBase: vi.fn().mockResolvedValue(kb()),
    deleteKnowledgeBase: vi.fn().mockResolvedValue(undefined),
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    getDocument: vi.fn(),
    deleteDocument: vi.fn(),
    getDocumentChunks: vi.fn(),
    reprocessDocument: vi.fn(),
    getDocumentLocation: vi.fn(),
    withAdapter: vi.fn(),
    ...overrides,
  }
}

function renderPage(
  api: KnowledgeApi,
  initialEntry = '/knowledge-bases',
  currentUser: UserSummary | null = null,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route
              path="/knowledge-bases"
              element={<KnowledgeBaseListPage api={api} currentUser={currentUser} />}
            />
            <Route path="/knowledge-bases/:kbId" element={<div>知识库详情</div>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('知识库列表页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染知识库 Ledger 行并同时用文字与视觉标记可见性', async () => {
    renderPage(makeApi())

    expect(await screen.findByText('合规资料')).toBeInTheDocument()
    const row = screen.getByText('合规资料').closest('li')
    expect(row).toBeInTheDocument()
    expect(screen.getByText('私有')).toBeInTheDocument()
    expect(screen.getByText('内部合规制度')).toBeInTheDocument()
    // 进入详情按钮
    expect(screen.getByRole('link', { name: '进入知识库' })).toHaveAttribute(
      'href',
      `/knowledge-bases/${KB_UUID}`,
    )
  })

  it('最近更新列用绝对时间戳（不用相对时间）', async () => {
    renderPage(makeApi()) // fixture: updated_at=2026-08-08T00:00:00Z
    await screen.findByText('合规资料')

    expect(screen.getByText(formatTimestamp(kb().updated_at))).toBeInTheDocument()
    expect(screen.queryByText(/刚刚|分钟前/)).not.toBeInTheDocument()
  })

  it('展示 public 可见性为文字「公开」', async () => {
    renderPage(
      makeApi({
        listKnowledgeBases: vi.fn().mockResolvedValue({
          total: 1,
          page: 1,
          page_size: 20,
          items: [kb({ visibility: 'public' })],
        }),
      }),
    )

    expect(await screen.findByText('公开')).toBeInTheDocument()
  })

  it('Ledger 表头含索引状态列，且索引状态来自权威字段', async () => {
    renderPage(
      makeApi({
        listKnowledgeBases: vi.fn().mockResolvedValue({
          total: 1,
          page: 1,
          page_size: 20,
          items: [kb({ index_status: 'updating' })],
        }),
      }),
    )

    expect(await screen.findByText('合规资料')).toBeInTheDocument()
    expect(screen.getByText('索引状态')).toBeInTheDocument()
    expect(screen.getByText('索引更新中')).toBeInTheDocument()
  })

  it('索引状态缺失时展示占位而非猜测文案', async () => {
    renderPage(
      makeApi({
        listKnowledgeBases: vi.fn().mockResolvedValue({
          total: 1,
          page: 1,
          page_size: 20,
          items: [kb({ index_status: null })],
        }),
      }),
    )

    expect(await screen.findByText('合规资料')).toBeInTheDocument()
    expect(screen.queryByText('可检索')).not.toBeInTheDocument()
  })

  it('切换范围筛选后以新 scope 重新请求', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('合规资料')
    fireEvent.click(screen.getByRole('button', { name: '我创建的' }))

    await waitFor(() =>
      expect(api.listKnowledgeBases).toHaveBeenLastCalledWith(
        expect.objectContaining({ scope: 'mine' }),
      ),
    )
  })

  it('提交名称搜索后以 q 重新请求', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('合规资料')
    const search = screen.getByRole('searchbox', { name: '搜索知识库' })
    fireEvent.change(search, { target: { value: '合规' } })
    fireEvent.submit(screen.getByRole('search', { name: '搜索知识库' }))

    await waitFor(() =>
      expect(api.listKnowledgeBases).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: '合规' }),
      ),
    )
  })

  it('创建知识库：打开抽屉填写名称并提交', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('合规资料')
    fireEvent.click(screen.getByRole('button', { name: '新建知识库' }))
    const nameInput = await screen.findByLabelText('知识库名称')
    fireEvent.change(nameInput, { target: { value: '产品文档' } })
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() =>
      expect(api.createKnowledgeBase).toHaveBeenCalledWith(
        expect.objectContaining({ name: '产品文档', visibility: 'private' }),
      ),
    )
  })

  it('切换范围时清除名称搜索（搜索关键字可能只匹配某一范围）', async () => {
    const api = makeApi()
    renderPage(api, '/knowledge-bases?scope=mine&q=合规')

    await screen.findByText('合规资料')
    fireEvent.click(screen.getByRole('button', { name: '全部' }))

    await waitFor(() =>
      expect(api.listKnowledgeBases).toHaveBeenLastCalledWith(
        expect.objectContaining({ scope: 'all', q: '' }),
      ),
    )
  })

  it('搜索无匹配时展示搜索空态，不重复显示新建按钮', async () => {
    renderPage(
      makeApi({
        listKnowledgeBases: vi.fn().mockResolvedValue({
          total: 0,
          page: 1,
          page_size: 20,
          items: [],
        }),
      }),
      '/knowledge-bases?q=不存在的名称',
    )

    expect(await screen.findByText('没有匹配的知识库')).toBeInTheDocument()
    // 搜索空态只保留页面头部主按钮，空态内不重复显示「新建知识库」
    expect(screen.getAllByRole('button', { name: '新建知识库' })).toHaveLength(1)
  })

  it('无知识库时展示空态与创建入口', async () => {
    renderPage(
      makeApi({
        listKnowledgeBases: vi.fn().mockResolvedValue({
          total: 0,
          page: 1,
          page_size: 20,
          items: [],
        }),
      }),
    )

    expect(await screen.findByText('还没有知识库')).toBeInTheDocument()
    // 页面头部与空态各提供一个创建入口
    expect(screen.getAllByRole('button', { name: '新建知识库' }).length).toBeGreaterThanOrEqual(2)
  })

  it('Owner 行操作列：进入知识库 + ⋮ 菜单（编辑/删除知识库）', async () => {
    renderPage(makeApi(), '/knowledge-bases', OWNER)
    await screen.findByText('合规资料')

    // 行内主操作仍是「进入知识库」；编辑/删除收敛到 ⋮ 溢出菜单
    expect(screen.getByRole('link', { name: '进入知识库' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '知识库操作 合规资料' }))
    expect(screen.getByRole('menuitem', { name: '编辑' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: '删除知识库' })).toBeInTheDocument()
  })

  it('只读成员（非 owner 非 admin）行操作列不显示 ⋮ 溢出菜单', async () => {
    renderPage(makeApi(), '/knowledge-bases', READONLY_MEMBER)
    await screen.findByText('合规资料')

    expect(screen.getByRole('link', { name: '进入知识库' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /知识库操作/ })).not.toBeInTheDocument()
  })

  it('管理员非 owner 治理可见 ⋮ 菜单（编辑/删除知识库）', async () => {
    renderPage(makeApi(), '/knowledge-bases', ADMIN_NON_OWNER)
    await screen.findByText('合规资料')

    fireEvent.click(screen.getByRole('button', { name: '知识库操作 合规资料' }))
    expect(screen.getByRole('menuitem', { name: '编辑' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: '删除知识库' })).toBeInTheDocument()
  })

  it('删除知识库：⋮ → 具名确认 → 调用删除并移除行 + 全局成功反馈', async () => {
    const api = makeApi()
    // 删除后列表接口不再返回该 KB（与真实后端一致），验证行从列表消失
    let deleted = false
    api.deleteKnowledgeBase = vi.fn().mockImplementation(() => {
      deleted = true
      return Promise.resolve(undefined)
    })
    api.listKnowledgeBases = vi.fn().mockImplementation(() =>
      Promise.resolve({
        total: deleted ? 0 : 1,
        page: 1,
        page_size: 20,
        items: deleted ? [] : [kb()],
      }),
    )
    renderPage(api, '/knowledge-bases', OWNER)
    await screen.findByText('合规资料')

    fireEvent.click(screen.getByRole('button', { name: '知识库操作 合规资料' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '删除知识库' }))
    expect(await screen.findByText(/确定删除知识库「合规资料」/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(api.deleteKnowledgeBase).toHaveBeenCalledWith(KB_UUID))
    await waitFor(() => expect(screen.queryByText('合规资料')).not.toBeInTheDocument())
    expect(await screen.findByText(/已删除知识库「合规资料」/)).toBeInTheDocument()
  })

  it('编辑知识库：⋮ → 抽屉预填并保存后调用 updateKnowledgeBase', async () => {
    const api = makeApi()
    renderPage(api, '/knowledge-bases', OWNER)
    await screen.findByText('合规资料')

    fireEvent.click(screen.getByRole('button', { name: '知识库操作 合规资料' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '编辑' }))
    const dialog = await screen.findByRole('dialog', { name: '编辑知识库' })
    const nameInput = within(dialog).getByLabelText('知识库名称')
    expect(nameInput).toHaveValue('合规资料')
    fireEvent.change(nameInput, { target: { value: '合规资料 V2' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(api.updateKnowledgeBase).toHaveBeenCalledWith(
        KB_UUID,
        expect.objectContaining({ name: '合规资料 V2' }),
      ),
    )
  })

  it('底部说明哪些文档会参与检索', async () => {
    renderPage(makeApi())
    await screen.findByText('合规资料')

    expect(
      screen.getByText(/只有已完成或部分完成且具有有效来源的文档会参与检索/),
    ).toBeInTheDocument()
  })
})
