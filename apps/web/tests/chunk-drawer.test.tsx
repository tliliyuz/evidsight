import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChunkDrawer } from '@/features/knowledge/ChunkDrawer'
import type { KnowledgeApi } from '@/api/knowledge'

const DOC_UUID = '550e8400-e29b-41d4-a716-446655440200'
const SEGMENT_UUID = '550e8400-e29b-41d4-a716-446655440300'
const SEGMENT_UUID_2 = '550e8400-e29b-41d4-a716-446655440301'

function makeApi(overrides: Partial<KnowledgeApi> = {}): KnowledgeApi {
  return {
    listKnowledgeBases: vi.fn(),
    createKnowledgeBase: vi.fn(),
    updateKnowledgeBase: vi.fn(),
    deleteKnowledgeBase: vi.fn(),
    getKnowledgeBase: vi.fn(),
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    getDocument: vi.fn(),
    deleteDocument: vi.fn(),
    getDocumentChunks: vi.fn().mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [
        {
          id: 41,
          segment_id: SEGMENT_UUID,
          chunk_index: 0,
          preview: '第一段安全预览',
          token_count: 12,
          metadata: { page: 3 },
        },
        {
          id: 42,
          segment_id: SEGMENT_UUID_2,
          chunk_index: 1,
          preview: '第二段安全预览',
          token_count: 8,
          metadata: { page: 4 },
        },
      ],
    }),
    reprocessDocument: vi.fn(),
    getDocumentLocation: vi.fn().mockResolvedValue({
      document_id: DOC_UUID,
      segment_id: SEGMENT_UUID,
      minimal_excerpt: '第 3 页实际正文片段',
      location: { page_number: 3 },
      source_updated_at: null,
    }),
    withAdapter: vi.fn(),
    ...overrides,
  }
}

function renderDrawer(api: KnowledgeApi) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ChunkDrawer documentId={DOC_UUID} api={api} onClose={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe('文档切片抽屉', () => {
  beforeEach(() => vi.clearAllMocks())

  it('展示分块列表（segment_id、预览、Token 数）而不依赖内部整数 id', async () => {
    renderDrawer(makeApi())

    expect(await screen.findByText('第一段安全预览')).toBeInTheDocument()
    expect(screen.getByText('第二段安全预览')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    // 内部整数 id 不作为契约暴露
    expect(screen.queryByText('41')).not.toBeInTheDocument()
  })

  it('展开切片时以稳定 segment_id 实时请求 location 正文', async () => {
    const api = makeApi()
    renderDrawer(api)

    fireEvent.click(await screen.findByRole('button', { name: '展开第一段' }))

    await waitFor(() =>
      expect(api.getDocumentLocation).toHaveBeenCalledWith(DOC_UUID, SEGMENT_UUID),
    )
    expect(await screen.findByText('第 3 页实际正文片段')).toBeInTheDocument()
  })

  it('展开第二个切片时用其自身的 segment_id 请求', async () => {
    const api = makeApi()
    renderDrawer(api)

    fireEvent.click(await screen.findByRole('button', { name: '展开第二段' }))

    await waitFor(() =>
      expect(api.getDocumentLocation).toHaveBeenCalledWith(DOC_UUID, SEGMENT_UUID_2),
    )
  })

  it('权限撤销（403）后立即清除已显示正文并展示不可访问状态', async () => {
    const api = makeApi()
    const { getDocumentLocation } = api
    ;(getDocumentLocation as ReturnType<typeof vi.fn>).mockImplementation(() => {
      const err = new Error('无权限访问该来源') as Error & { response: { status: number } }
      err.response = { status: 403 }
      return Promise.reject(err)
    })
    renderDrawer(api)

    fireEvent.click(await screen.findByRole('button', { name: '展开第一段' }))

    expect(await screen.findByText('原文已不可访问')).toBeInTheDocument()
    expect(screen.queryByText('第 3 页实际正文片段')).not.toBeInTheDocument()
    // 元数据保留，正文被清除
    expect(screen.getByText('第一段安全预览')).toBeInTheDocument()
  })

  it('E2015 来源不可用时同样清正文并显示受限态', async () => {
    const api = makeApi()
    const { getDocumentLocation } = api
    ;(getDocumentLocation as ReturnType<typeof vi.fn>).mockImplementation(() => {
      const err = new Error('来源不可用') as Error & { response: { status: 404 } }
      err.response = { status: 404 }
      return Promise.reject(err)
    })
    renderDrawer(api)

    fireEvent.click(await screen.findByRole('button', { name: '展开第一段' }))

    expect(await screen.findByText('原文已不可访问')).toBeInTheDocument()
  })

  it('E2015 错误码显式识别（非 404 状态）同样受限', async () => {
    const api = makeApi()
    const { getDocumentLocation } = api
    ;(getDocumentLocation as ReturnType<typeof vi.fn>).mockImplementation(() => {
      const err = new Error('来源不可用') as Error & {
        response: { status: number; data: { error: { error_code: string } } }
      }
      err.response = { status: 200, data: { error: { error_code: 'E2015' } } }
      return Promise.reject(err)
    })
    renderDrawer(api)

    fireEvent.click(await screen.findByRole('button', { name: '展开第一段' }))

    expect(await screen.findByText('原文已不可访问')).toBeInTheDocument()
  })

  it('相邻切片基于当前分块列表切换展开', async () => {
    const api = makeApi()
    renderDrawer(api)

    fireEvent.click(await screen.findByRole('button', { name: '展开第一段' }))
    await screen.findByText('第 3 页实际正文片段')

    // 第一段有「下一段」，点击后按第二段的 segment_id 重新鉴权请求
    fireEvent.click(screen.getByRole('button', { name: /下一段/ }))

    await waitFor(() =>
      expect(api.getDocumentLocation).toHaveBeenCalledWith(DOC_UUID, SEGMENT_UUID_2),
    )
  })
})
