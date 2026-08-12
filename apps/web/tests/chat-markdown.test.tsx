import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { hasInlineCitations, renderChatMarkdown } from '@/features/chat/chatMarkdown'
import { sourceLocation } from '@/features/chat/chatFormat'
import type { ChatSourceChunk } from '@/features/chat/chatSseParser'

const SOURCE_1: ChatSourceChunk = {
  chunk_index: 1,
  document_uuid: 'doc-1',
  segment_id: 'seg-1',
  doc_name: '复盘报告.pdf',
  score: 0.9,
  page: 18,
  section_title: null,
  section_path: null,
  preview_text: null,
  preview_range: null,
  highlight_start: null,
  highlight_end: null,
}

const SOURCE_2: ChatSourceChunk = {
  chunk_index: 2,
  document_uuid: 'doc-2',
  segment_id: 'seg-2',
  doc_name: 'Day 3 全天纪实.docx',
  score: 0.8,
  page: 385,
  section_title: null,
  section_path: null,
  preview_text: null,
  preview_range: null,
  highlight_start: null,
  highlight_end: null,
}

describe('回答 markdown 渲染（chatMarkdown）', () => {
  it('hasInlineCitations 识别 [来源N] 标记', () => {
    expect(hasInlineCitations('统一工作台 [来源1][来源2]')).toBe(true)
    expect(hasInlineCitations('普通文本')).toBe(false)
  })

  it('渲染粗体 / 斜体 / 行内代码', () => {
    render(<div>{renderChatMarkdown('**功能特点** 与 `code` 和 *斜体*', [], () => {})}</div>)
    expect(screen.getByText('功能特点').tagName).toBe('STRONG')
    expect(screen.getByText('code').tagName).toBe('CODE')
    expect(screen.getByText('斜体').tagName).toBe('EM')
  })

  it('渲染无序列表', () => {
    render(<div>{renderChatMarkdown('- 第一项\n- 第二项', [], () => {})}</div>)
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('第一项')).toBeInTheDocument()
  })

  it('把 [来源N] 转成内联引用按钮并点击回调', () => {
    const onOpenSource = vi.fn()
    render(
      <div>
        {renderChatMarkdown('统一工作台 [来源1][来源2]', [SOURCE_1, SOURCE_2], onOpenSource)}
      </div>,
    )
    fireEvent.click(screen.getByRole('button', { name: '引用来源 2' }))
    expect(onOpenSource).toHaveBeenCalledWith(SOURCE_2)
  })
})

describe('来源定位（PDF 页 / 其它 段）', () => {
  it('PDF 文档显示「第 X 页」', () => {
    expect(sourceLocation(SOURCE_1)).toBe('第 18 页')
  })

  it('docx 文档的 page 实为段落序号，显示「第 X 段」', () => {
    expect(sourceLocation(SOURCE_2)).toBe('第 385 段')
  })
})
