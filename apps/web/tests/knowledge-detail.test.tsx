import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserSummary } from '@/api/auth'
import { ToastProvider } from '@/components/feedback/ToastProvider'
import { KnowledgeBaseDetailPage } from '@/features/knowledge/KnowledgeBaseDetailPage'
import { formatTimestamp } from '@/features/knowledge/format'
import type {
  Document,
  DocumentStatus,
  DocumentUpload,
  KnowledgeApi,
  KnowledgeBase,
} from '@/api/knowledge'

const KB_UUID = '550e8400-e29b-41d4-a716-446655440100'
const DOC_UUID = '550e8400-e29b-41d4-a716-446655440200'
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
    doc_count: 1,
    chunk_count: 18,
    index_status: 'ready',
    owner_username: 'linmo',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-08T00:00:00Z',
    ...overrides,
  }
}

function doc(status: DocumentStatus = 'completed'): Document {
  return {
    uuid: DOC_UUID,
    kb_uuid: KB_UUID,
    filename: '制度汇编.pdf',
    file_type: 'pdf',
    file_size: 2048,
    status,
    chunk_count: 6,
    error_msg: null,
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-06T00:00:00Z',
  }
}

function makeApi(overrides: Partial<KnowledgeApi> = {}): KnowledgeApi {
  return {
    listKnowledgeBases: vi.fn(),
    createKnowledgeBase: vi.fn(),
    updateKnowledgeBase: vi.fn(),
    deleteKnowledgeBase: vi.fn(),
    getKnowledgeBase: vi.fn().mockResolvedValue(kb()),
    listDocuments: vi.fn().mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [doc()],
    }),
    uploadDocument: vi.fn().mockResolvedValue({
      uuid: DOC_UUID,
      kb_uuid: KB_UUID,
      filename: '制度汇编.pdf',
      file_type: 'pdf',
      file_size: 2048,
      status: 'queued',
    }),
    getDocument: vi.fn(),
    deleteDocument: vi.fn().mockResolvedValue(undefined),
    getDocumentChunks: vi.fn(),
    reprocessDocument: vi.fn().mockResolvedValue({ doc_uuid: DOC_UUID, status: 'partial' }),
    getDocumentLocation: vi.fn(),
    withAdapter: vi.fn(),
    ...overrides,
  }
}

function renderPage(
  api: KnowledgeApi,
  currentUser: UserSummary | null = OWNER,
  initialEntry = `/knowledge-bases/${KB_UUID}`,
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
              path="/knowledge-bases/:kbId"
              element={<KnowledgeBaseDetailPage api={api} currentUser={currentUser} />}
            />
            <Route path="/knowledge-bases" element={<div>知识库列表</div>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('知识库详情与文档管理', () => {
  beforeEach(() => vi.clearAllMocks())

  it('展示知识库 Hero 元数据与文档列表', async () => {
    renderPage(makeApi())

    expect(await screen.findByRole('heading', { name: '合规资料' })).toBeInTheDocument()
    expect(screen.getByText('内部合规制度')).toBeInTheDocument()
    // owner 用户名出现在 Hero（后端权威 owner_username）
    expect(screen.getByText('linmo 创建')).toBeInTheDocument()
    expect(await screen.findByText('制度汇编.pdf')).toBeInTheDocument()
  })

  it('Hero 提供「用它提问」按钮，跳转问答页并预选当前知识库', async () => {
    renderPage(makeApi())

    await screen.findByRole('heading', { name: '合规资料' })
    expect(screen.getByRole('link', { name: '用它提问' })).toHaveAttribute(
      'href',
      `/chat?kb=${KB_UUID}`,
    )
  })

  it('Hero 更新时间用绝对时间戳（不用「刚刚/分钟前」相对时间）', async () => {
    renderPage(makeApi())
    await screen.findByRole('heading', { name: '合规资料' })

    expect(screen.getByText(`${formatTimestamp(kb().updated_at)} 更新`)).toBeInTheDocument()
    expect(screen.queryByText(/刚刚|分钟前/)).not.toBeInTheDocument()
  })

  it('Hero 状态行顺序：owner 创建在可见性徽章左侧', async () => {
    renderPage(makeApi()) // 默认 private + linmo 创建
    await screen.findByRole('heading', { name: '合规资料' })

    const meta = document.querySelector('.detail-hero__meta') as HTMLElement
    const order = [...meta.children].map((el) => el.textContent?.trim() ?? '')
    expect(order[0]).toBe('linmo 创建')
    expect(order[1]).toBe('私有')
    expect(order[2]).toMatch(/ 更新$/)
  })

  it('owner 用户名缺省时回退到当前用户（owner）的 /me 用户名', async () => {
    renderPage(
      makeApi({
        getKnowledgeBase: vi.fn().mockResolvedValue(kb({ owner_username: null })),
      }),
      OWNER,
    )
    await screen.findByRole('heading', { name: '合规资料' })

    // 后端未返回 owner_username 时，owner 仍能看到自己的用户名（来自 /me）
    expect(screen.getByText('linmo 创建')).toBeInTheDocument()
  })

  it('owner 用户名缺省且当前用户非 owner 时不展示创建者（不伪造他人用户名）', async () => {
    renderPage(
      makeApi({
        getKnowledgeBase: vi.fn().mockResolvedValue(kb({ owner_username: null })),
      }),
      READONLY_MEMBER,
    )
    await screen.findByRole('heading', { name: '合规资料' })

    expect(screen.queryByText(/ 创建$/)).not.toBeInTheDocument()
  })

  it('展示知识库摘要卡片：文档总数/分块总数/创建时间（绝对时间戳）', async () => {
    renderPage(makeApi()) // fixture: doc_count=1, chunk_count=18, created_at=2026-08-01T00:00:00Z
    const strip = await screen.findByRole('region', { name: '知识库摘要' })

    expect(within(strip).getByText('文档总数')).toBeInTheDocument()
    expect(within(strip).getByText('1')).toBeInTheDocument()
    expect(within(strip).getByText('分块总数')).toBeInTheDocument()
    expect(within(strip).getByText('18')).toBeInTheDocument()
    expect(within(strip).getByText('创建时间')).toBeInTheDocument()
    expect(within(strip).getByText(formatTimestamp(kb().created_at))).toBeInTheDocument()
  })

  it('文档列表「更新时间」列用绝对时间戳', async () => {
    renderPage(makeApi()) // fixture: doc updated_at=2026-08-06T00:00:00Z
    await screen.findByText('制度汇编.pdf')

    const row = screen.getByText('制度汇编.pdf').closest('li') as HTMLElement
    expect(within(row).getByText(formatTimestamp(doc().updated_at))).toBeInTheDocument()
    expect(within(row).queryByText(/刚刚|分钟前/)).not.toBeInTheDocument()
  })

  it('Hero 可见性徽章：public 用 knowledge 蓝、private 用中性灰（不再同灰）', async () => {
    const api = makeApi({
      getKnowledgeBase: vi.fn().mockResolvedValue(kb({ visibility: 'public' })),
    })
    const { unmount } = renderPage(api)

    const publicBadge = await screen.findByText('公开')
    expect(publicBadge.closest('.status-badge') as HTMLElement).toHaveClass(
      'status-badge--knowledge',
    )
    unmount()

    renderPage(makeApi()) // 默认 private
    const privateBadge = await screen.findByText('私有')
    expect(privateBadge.closest('.status-badge') as HTMLElement).toHaveClass(
      'status-badge--neutral',
    )
  })

  it('提供返回知识库入口', async () => {
    renderPage(makeApi())
    await screen.findByRole('heading', { name: '合规资料' })

    expect(screen.getByRole('link', { name: /返回知识库/ })).toHaveAttribute(
      'href',
      '/knowledge-bases',
    )
  })

  it('六值文档状态映射到业务文案与独立徽章色', async () => {
    // 每个状态独立色调：仅 completed（可检索）为 success 绿，queued/deleting 为中性灰
    const cases: { status: DocumentStatus; label: string; tone: string }[] = [
      { status: 'queued', label: '等待处理', tone: 'status-badge--neutral' },
      { status: 'processing', label: '处理中', tone: 'status-badge--processing' },
      { status: 'completed', label: '可检索', tone: 'status-badge--success' },
      { status: 'partial', label: '部分可用', tone: 'status-badge--warning' },
      { status: 'failed', label: '处理失败', tone: 'status-badge--danger' },
      { status: 'deleting', label: '删除中', tone: 'status-badge--neutral' },
    ]
    for (const { status, label, tone } of cases) {
      const api = makeApi({
        listDocuments: vi.fn().mockResolvedValue({
          total: 1,
          page: 1,
          page_size: 20,
          items: [doc(status)],
        }),
      })
      const { unmount } = renderPage(api)
      // 状态标签出现在文档行内（状态筛选下拉也含相同文案，需限定在行内断言）
      const row = (await screen.findByText('制度汇编.pdf')).closest('li')
      const cell = within(row as HTMLElement).getByText(label)
      expect(cell).toBeInTheDocument()
      expect(cell.closest('.status-badge') as HTMLElement).toHaveClass(tone)
      unmount()
    }
  })

  it('上传抽屉校验扩展名并拒绝非法格式', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    fireEvent.click(screen.getByRole('button', { name: '上传文档' }))
    const input = await screen.findByLabelText('选择文件')
    const invalid = new File(['bad'], '脚本.exe', { type: 'application/octet-stream' })
    fireEvent.change(input, { target: { files: [invalid] } })

    expect(await screen.findByText(/仅支持 PDF、DOCX、Markdown、TXT/)).toBeInTheDocument()
    expect(api.uploadDocument).not.toHaveBeenCalled()
  })

  it('上传合法 PDF 后调用 uploadDocument 并提交表单', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    fireEvent.click(screen.getByRole('button', { name: '上传文档' }))
    const input = await screen.findByLabelText('选择文件')
    const valid = new File(['%PDF-1.7 fake'], '新制度.pdf', { type: 'application/pdf' })
    fireEvent.change(input, { target: { files: [valid] } })
    fireEvent.click(screen.getByRole('button', { name: '开始上传' }))

    await waitFor(() => expect(api.uploadDocument).toHaveBeenCalled())
    expect(api.uploadDocument).toHaveBeenCalledWith(
      KB_UUID,
      expect.any(File),
      expect.any(Boolean),
      expect.any(AbortSignal),
    )
    // 上传完成返回详情页：抽屉关闭
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('支持多文件选择并展示待上传队列', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    fireEvent.click(screen.getByRole('button', { name: '上传文档' }))
    const input = await screen.findByLabelText('选择文件')
    const a = new File(['%PDF'], '报告.pdf', { type: 'application/pdf' })
    const b = new File(['# 记录'], '会议记录.md', { type: 'text/markdown' })
    fireEvent.change(input, { target: { files: [a, b] } })

    expect(await screen.findByText('报告.pdf')).toBeInTheDocument()
    expect(screen.getByText('会议记录.md')).toBeInTheDocument()
    expect(screen.getAllByText('就绪')).toHaveLength(2)
  })

  it('取消上传中止进行中的上传批次', async () => {
    let capturedSignal: AbortSignal | undefined
    const api = makeApi({
      uploadDocument: vi.fn((_kb: string, _file: File, _force?: boolean, signal?: AbortSignal) => {
        capturedSignal = signal
        return new Promise<DocumentUpload>((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            reject(new DOMException('已中止', 'AbortError'))
          })
        })
      }),
    })
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    fireEvent.click(screen.getByRole('button', { name: '上传文档' }))
    const input = await screen.findByLabelText('选择文件')
    fireEvent.change(input, {
      target: { files: [new File(['%PDF'], '新制度.pdf', { type: 'application/pdf' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始上传' }))

    await screen.findByText('上传中')
    fireEvent.click(screen.getByRole('button', { name: '取消上传' }))

    expect(capturedSignal?.aborted).toBe(true)
    expect(await screen.findByText('已取消')).toBeInTheDocument()
  })

  it('存在非终态文档（queued）时轮询刷新文档状态', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const api = makeApi({
        listDocuments: vi.fn().mockResolvedValue({
          total: 1,
          page: 1,
          page_size: 20,
          items: [doc('queued')],
        }),
      })
      renderPage(api)
      await screen.findByText('制度汇编.pdf')
      const callsBefore = (api.listDocuments as ReturnType<typeof vi.fn>).mock.calls.length
      await act(async () => {
        vi.advanceTimersByTime(6000)
      })
      expect((api.listDocuments as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(
        callsBefore,
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('全部文档进入终态后停止轮询', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const api = makeApi() // 默认 completed（终态）
      renderPage(api)
      await screen.findByText('制度汇编.pdf')
      const callsBefore = (api.listDocuments as ReturnType<typeof vi.fn>).mock.calls.length
      await act(async () => {
        vi.advanceTimersByTime(6000)
      })
      expect((api.listDocuments as ReturnType<typeof vi.fn>).mock.calls.length).toBe(callsBefore)
    } finally {
      vi.useRealTimers()
    }
  })

  it('failed 文档提供重试操作', async () => {
    const api = makeApi({
      listDocuments: vi.fn().mockResolvedValue({
        total: 1,
        page: 1,
        page_size: 20,
        items: [doc('failed')],
      }),
    })
    renderPage(api)

    const retryButton = await screen.findByRole('button', { name: '重试' })
    fireEvent.click(retryButton)

    await waitFor(() => expect(api.reprocessDocument).toHaveBeenCalledWith(DOC_UUID))
  })

  it('删除文档：具名二次确认后调用 deleteDocument，成功后弹成功反馈', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    fireEvent.click(screen.getByRole('button', { name: '删除文档' }))
    expect(await screen.findByText(/确定删除文档/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith(DOC_UUID))
    expect(await screen.findByText(/已删除文档「制度汇编.pdf」/)).toBeInTheDocument()
  })

  it('筛选无匹配时展示筛选空态而非「还没有文档」', async () => {
    renderPage(
      makeApi({
        listDocuments: vi.fn().mockResolvedValue({
          total: 0,
          page: 1,
          page_size: 20,
          items: [],
        }),
      }),
      OWNER,
      '/knowledge-bases/550e8400-e29b-41d4-a716-446655440100?status=failed',
    )

    expect(await screen.findByText('没有匹配的文档')).toBeInTheDocument()
    expect(screen.queryByText('还没有文档')).not.toBeInTheDocument()
  })

  it('owner 可见上传与文档操作；知识库编辑/删除不在详情页（收敛到列表 ⋮ 菜单）', async () => {
    const api = makeApi({
      listDocuments: vi.fn().mockResolvedValue({
        total: 1,
        page: 1,
        page_size: 20,
        items: [doc('failed')],
      }),
    })
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    expect(screen.getByRole('button', { name: '上传文档' })).toBeInTheDocument()
    // 编辑/删除知识库已收敛到列表 ⋮ 菜单，详情 Hero 不再提供
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除知识库' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除文档' })).toBeInTheDocument()
  })

  it('普通只读成员（非 owner 非 admin）不可见上传、编辑、删除', async () => {
    renderPage(makeApi(), READONLY_MEMBER)
    await screen.findByText('制度汇编.pdf')

    expect(screen.queryByRole('button', { name: '上传文档' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除知识库' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除文档' })).not.toBeInTheDocument()
  })

  it('管理员非 owner：治理可见文档删除，但不可代替 owner 上传/重试', async () => {
    const api = makeApi({
      listDocuments: vi.fn().mockResolvedValue({
        total: 1,
        page: 1,
        page_size: 20,
        items: [doc('failed')],
      }),
    })
    renderPage(api, ADMIN_NON_OWNER)

    await screen.findByText('制度汇编.pdf')
    expect(screen.queryByRole('button', { name: '上传文档' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
    // 知识库编辑/删除不在详情页；文档删除仍按治理权限可见
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除知识库' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除文档' })).toBeInTheDocument()
  })

  it('Public KB 的 owner 仍可见上传入口（不按 visibility 判断）', async () => {
    const api = makeApi({
      getKnowledgeBase: vi.fn().mockResolvedValue(kb({ visibility: 'public' })),
    })
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    expect(screen.getByRole('button', { name: '上传文档' })).toBeInTheDocument()
  })

  it('状态筛选选择后以对应 status 重新请求', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    fireEvent.change(screen.getByLabelText('状态筛选'), { target: { value: 'failed' } })

    await waitFor(() =>
      expect(api.listDocuments).toHaveBeenLastCalledWith(
        KB_UUID,
        expect.objectContaining({ status: 'failed', page: 1 }),
      ),
    )
  })

  it('文件名搜索提交后以 filename 重新请求', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    const search = screen.getByRole('searchbox', { name: '搜索文档' })
    fireEvent.change(search, { target: { value: '制度' } })
    fireEvent.submit(screen.getByRole('search', { name: '搜索文档' }))

    await waitFor(() =>
      expect(api.listDocuments).toHaveBeenLastCalledWith(
        KB_UUID,
        expect.objectContaining({ filename: '制度', page: 1 }),
      ),
    )
  })

  it('页脚说明上传后可离开、后台继续处理', async () => {
    renderPage(makeApi())
    await screen.findByText('制度汇编.pdf')

    expect(screen.getByText(/上传完成后即可离开此页/)).toBeInTheDocument()
  })
})
