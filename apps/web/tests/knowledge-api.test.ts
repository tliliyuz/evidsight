import type { AxiosAdapter, AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it } from 'vitest'

import { knowledgeApi } from '@/api/knowledge'

function response(
  config: Parameters<AxiosAdapter>[0],
  status: number,
  data: unknown,
): AxiosResponse {
  return {
    config,
    status,
    statusText: String(status),
    headers: {},
    data,
  }
}

function envelope(data: unknown) {
  return { code: '0', message: 'ok', data }
}

let calls: { url: string; params?: Record<string, unknown> }[] = []

beforeEach(() => {
  calls = []
})

describe('Knowledge v1 API 客户端', () => {
  it('列出知识库时传递 scope/q/分页查询参数并解包信封', async () => {
    const list = { total: 1, page: 1, page_size: 20, items: [] }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '', params: config.params })
      return response(config, 200, envelope(list))
    }
    const client = knowledgeApi.withAdapter(adapter)

    const data = await client.listKnowledgeBases({ scope: 'public', q: '合规', page: 2 })

    expect(data).toEqual(list)
    expect(calls[0].url).toBe('/api/v1/knowledge-bases')
    expect(calls[0].params).toMatchObject({ scope: 'public', q: '合规', page: 2, page_size: 20 })
  })

  it('scope 缺省为 all', async () => {
    const list = { total: 0, page: 1, page_size: 20, items: [] }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '', params: config.params })
      return response(config, 200, envelope(list))
    }
    const data = await knowledgeApi.withAdapter(adapter).listKnowledgeBases({})

    expect(calls[0].params).toMatchObject({ scope: 'all' })
    expect(data.items).toEqual([])
  })

  it('创建知识库 POST 到 /api/v1/knowledge-bases', async () => {
    const kb = {
      uuid: '550e8400-e29b-41d4-a716-446655440100',
      name: '合规资料',
      description: null,
      owner: '550e8400-e29b-41d4-a716-446655440001',
      visibility: 'private',
      status: 'active',
      doc_count: 0,
      chunk_count: 0,
      created_at: '2026-08-09T00:00:00Z',
      updated_at: null,
    }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '' })
      return response(config, 201, envelope(kb))
    }
    const data = await knowledgeApi
      .withAdapter(adapter)
      .createKnowledgeBase({ name: '合规资料', visibility: 'private' })

    expect(calls[0].url).toBe('/api/v1/knowledge-bases')
    expect(data.name).toBe('合规资料')
  })

  it('更新知识库 PATCH 到 /api/v1/knowledge-bases/{id}', async () => {
    const kb = {
      uuid: '550e8400-e29b-41d4-a716-446655440100',
      name: '新名称',
      description: null,
      owner: '550e8400-e29b-41d4-a716-446655440001',
      visibility: 'public',
      status: 'active',
      doc_count: 0,
      chunk_count: 0,
      created_at: '2026-08-09T00:00:00Z',
      updated_at: '2026-08-09T01:00:00Z',
    }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '' })
      return response(config, 200, envelope(kb))
    }
    const data = await knowledgeApi
      .withAdapter(adapter)
      .updateKnowledgeBase('550e8400-e29b-41d4-a716-446655440100', { name: '新名称' })

    expect(calls[0].url).toBe('/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440100')
    expect(data.visibility).toBe('public')
  })

  it('删除知识库 DELETE 到 /api/v1/knowledge-bases/{id} 并接受 204', async () => {
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '' })
      return response(config, 204, '')
    }
    await knowledgeApi
      .withAdapter(adapter)
      .deleteKnowledgeBase('550e8400-e29b-41d4-a716-446655440100')
    expect(calls[0].url).toBe('/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440100')
  })

  it('列出文档时传递 status/filename/sort 查询参数', async () => {
    const list = { total: 0, page: 1, page_size: 20, items: [] }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '', params: config.params })
      return response(config, 200, envelope(list))
    }
    await knowledgeApi.withAdapter(adapter).listDocuments('550e8400-e29b-41d4-a716-446655440100', {
      status: 'completed',
      filename: '报告',
      sort_by: 'updated_at',
      order: 'desc',
    })

    expect(calls[0].url).toBe(
      '/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440100/documents',
    )
    expect(calls[0].params).toMatchObject({
      status: 'completed',
      filename: '报告',
      sort_by: 'updated_at',
      order: 'desc',
    })
  })

  it('上传文档以 multipart 携带 file 与 force 到 KB documents 端点', async () => {
    const uploaded = {
      uuid: '550e8400-e29b-41d4-a716-446655440200',
      kb_uuid: '550e8400-e29b-41d4-a716-446655440100',
      filename: '测试文档.pdf',
      file_type: 'pdf',
      file_size: 1024,
      status: 'queued',
    }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '' })
      return response(config, 202, envelope(uploaded))
    }
    const file = new File(['%PDF-1.7 fake'], '测试文档.pdf', { type: 'application/pdf' })
    const data = await knowledgeApi
      .withAdapter(adapter)
      .uploadDocument('550e8400-e29b-41d4-a716-446655440100', file, true)

    expect(calls[0].url).toBe(
      '/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440100/documents',
    )
    expect(data.status).toBe('queued')
  })

  it('获取文档分块并返回稳定 segment_id', async () => {
    const chunkList = {
      total: 1,
      page: 1,
      page_size: 20,
      items: [
        {
          id: 41,
          segment_id: '550e8400-e29b-41d4-a716-446655440300',
          chunk_index: 0,
          preview: '安全预览',
          token_count: 10,
          metadata: { page: 3 },
        },
      ],
    }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '' })
      return response(config, 200, envelope(chunkList))
    }
    const data = await knowledgeApi
      .withAdapter(adapter)
      .getDocumentChunks('550e8400-e29b-41d4-a716-446655440200')

    expect(calls[0].url).toBe('/api/v1/documents/550e8400-e29b-41d4-a716-446655440200/chunks')
    expect(data.items[0].segment_id).toBe('550e8400-e29b-41d4-a716-446655440300')
  })

  it('按稳定 segment_id 实时获取文档来源位置', async () => {
    const location = {
      document_id: '550e8400-e29b-41d4-a716-446655440200',
      segment_id: '550e8400-e29b-41d4-a716-446655440300',
      minimal_excerpt: '第 3 页内容片段',
      location: { page_number: 3 },
      source_updated_at: null,
    }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '' })
      return response(config, 200, envelope(location))
    }
    const data = await knowledgeApi
      .withAdapter(adapter)
      .getDocumentLocation(
        '550e8400-e29b-41d4-a716-446655440200',
        '550e8400-e29b-41d4-a716-446655440300',
      )

    expect(calls[0].url).toBe(
      '/api/v1/documents/550e8400-e29b-41d4-a716-446655440200/locations/550e8400-e29b-41d4-a716-446655440300',
    )
    expect(data.minimal_excerpt).toBe('第 3 页内容片段')
  })

  it('文档重试 POST 到 retry 端点', async () => {
    const reprocess = {
      doc_uuid: '550e8400-e29b-41d4-a716-446655440200',
      status: 'partial',
    }
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '' })
      return response(config, 202, envelope(reprocess))
    }
    const data = await knowledgeApi
      .withAdapter(adapter)
      .reprocessDocument('550e8400-e29b-41d4-a716-446655440200')

    expect(calls[0].url).toBe('/api/v1/documents/550e8400-e29b-41d4-a716-446655440200/retry')
    expect(data.status).toBe('partial')
  })

  it('删除文档 DELETE 到 /api/v1/documents/{id} 并接受 204', async () => {
    const adapter: AxiosAdapter = async (config) => {
      calls.push({ url: config.url ?? '' })
      return response(config, 204, '')
    }
    await knowledgeApi.withAdapter(adapter).deleteDocument('550e8400-e29b-41d4-a716-446655440200')
    expect(calls[0].url).toBe('/api/v1/documents/550e8400-e29b-41d4-a716-446655440200')
  })
})
