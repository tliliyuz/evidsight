import { describe, expect, it } from 'vitest'

import { chatSourceToChunks } from '@/features/chat/chatSourceAdapter'

describe('chatSourceAdapter：持久化 ChatSource → SSE ChatSourceChunk', () => {
  it('完整映射保留全部字段', () => {
    const chunks = chatSourceToChunks([
      {
        chunk_index: 1,
        doc_name: '产品手册',
        score: 0.92,
        document_uuid: '550e8400-e29b-41d4-a716-446655440200',
        segment_id: '550e8400-e29b-41d4-a716-446655440300',
        page: 12,
        section_title: '采购标准',
        section_path: '文档 / 采购',
        preview_text: '权限继承需原样保留',
        preview_range: { start: 0, end: 4 },
        highlight_start: 0,
        highlight_end: 2,
      },
    ])

    expect(chunks).toEqual([
      {
        chunk_index: 1,
        doc_name: '产品手册',
        score: 0.92,
        document_uuid: '550e8400-e29b-41d4-a716-446655440200',
        segment_id: '550e8400-e29b-41d4-a716-446655440300',
        page: 12,
        section_title: '采购标准',
        section_path: '文档 / 采购',
        preview_text: '权限继承需原样保留',
        preview_range: { start: 0, end: 4 },
        highlight_start: 0,
        highlight_end: 2,
      },
    ])
  })

  it('nullable document_uuid/segment_id 归一为空字符串（不丢弃字段）', () => {
    const chunks = chatSourceToChunks([
      { chunk_index: 2, doc_name: '旧来源', score: 0.5, document_uuid: null, segment_id: null },
    ])

    expect(chunks[0].document_uuid).toBe('')
    expect(chunks[0].segment_id).toBe('')
  })

  it('nullable 元数据字段归一为 null', () => {
    const chunks = chatSourceToChunks([
      { chunk_index: 3, doc_name: '文档', score: 0.5, page: null, preview_range: null },
    ])

    expect(chunks[0].page).toBeNull()
    expect(chunks[0].section_title).toBeNull()
    expect(chunks[0].preview_text).toBeNull()
    expect(chunks[0].preview_range).toBeNull()
    expect(chunks[0].highlight_start).toBeNull()
    expect(chunks[0].highlight_end).toBeNull()
  })

  it('空数组返回空数组', () => {
    expect(chatSourceToChunks([])).toEqual([])
  })
})
