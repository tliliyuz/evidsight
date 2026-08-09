import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeBaseDetailPage } from '@/features/knowledge/KnowledgeBaseDetailPage'
import type { Document, DocumentStatus, KnowledgeApi, KnowledgeBase } from '@/api/knowledge'

const KB_UUID = '550e8400-e29b-41d4-a716-446655440100'
const DOC_UUID = '550e8400-e29b-41d4-a716-446655440200'

function kb(): KnowledgeBase {
  return {
    uuid: KB_UUID,
    name: '合规资料',
    description: '内部合规制度',
    owner: '550e8400-e29b-41d4-a716-446655440001',
    visibility: 'private',
    status: 'active',
    doc_count: 1,
    chunk_count: 18,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-08T00:00:00Z',
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

function renderPage(api: KnowledgeApi) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/knowledge-bases/${KB_UUID}`]}>
        <Routes>
          <Route path="/knowledge-bases/:kbId" element={<KnowledgeBaseDetailPage api={api} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('知识库详情与文档管理', () => {
  beforeEach(() => vi.clearAllMocks())

  it('展示知识库元数据与文档列表', async () => {
    renderPage(makeApi())

    expect(await screen.findByRole('heading', { name: '合规资料' })).toBeInTheDocument()
    expect(screen.getByText('内部合规制度')).toBeInTheDocument()
    expect(await screen.findByText('制度汇编.pdf')).toBeInTheDocument()
  })

  it('六值文档状态映射到业务文案', async () => {
    const cases: { status: DocumentStatus; label: string }[] = [
      { status: 'queued', label: '等待处理' },
      { status: 'processing', label: '处理中' },
      { status: 'completed', label: '可检索' },
      { status: 'partial', label: '部分可用' },
      { status: 'failed', label: '处理失败' },
      { status: 'deleting', label: '删除中' },
    ]
    for (const { status, label } of cases) {
      const api = makeApi({
        listDocuments: vi.fn().mockResolvedValue({
          total: 1,
          page: 1,
          page_size: 20,
          items: [doc(status)],
        }),
      })
      const { unmount } = renderPage(api)
      expect(await screen.findByText(label)).toBeInTheDocument()
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
    expect(api.uploadDocument).toHaveBeenCalledWith(KB_UUID, expect.any(File), expect.any(Boolean))
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

  it('删除文档：具名二次确认后调用 deleteDocument', async () => {
    const api = makeApi()
    renderPage(api)

    await screen.findByText('制度汇编.pdf')
    fireEvent.click(screen.getByRole('button', { name: '删除文档' }))
    expect(await screen.findByText(/确定删除文档/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith(DOC_UUID))
  })
})
