/**
 * ReportArticle 组件测试
 *
 * - Markdown 渲染
 * - citation-link 点击 emit
 * - data-evidence-index 空格分隔
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ReportArticle from '@/components/report/ReportArticle.vue'

describe('ReportArticle', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('渲染 Markdown 内容', () => {
    const wrapper = mount(ReportArticle, {
      props: {
        sections: [{ id: '0', heading: '概述', content: '# 标题\n\n正文段落。' }],
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.html()).toContain('<h1>标题</h1>')
    expect(wrapper.html()).toContain('<p>正文段落。')
  })

  it('[来源N] 渲染为 citation-link，展示索引从 1 开始且 data-evidence-index 仍为 0-based', () => {
    const wrapper = mount(ReportArticle, {
      props: {
        sections: [{ id: '0', heading: '概述', content: '参见 [来源0,1]。' }],
      },
      global: { plugins: [createPinia()] },
    })
    const link = wrapper.find('.citation-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('data-evidence-index')).toBe('0 1')
    expect(link.text()).toBe('[来源1,2]')
  })

  it('点击 citation-link emit citation-click', async () => {
    const wrapper = mount(ReportArticle, {
      props: {
        sections: [{ id: '0', heading: '概述', content: '参见 [来源3]。' }],
      },
      global: { plugins: [createPinia()] },
    })
    await wrapper.find('.citation-link').trigger('click')
    expect(wrapper.emitted('citation-click')).toHaveLength(1)
    expect(wrapper.emitted('citation-click')[0]).toEqual([3])
  })

  it('selectedSectionId 变化时滚动到对应 section', async () => {
    const wrapper = mount(ReportArticle, {
      props: {
        sections: [
          { id: '0', heading: '第一章', content: '内容一' },
          { id: '1', heading: '第二章', content: '内容二' },
        ],
      },
      global: { plugins: [createPinia()] },
      attachTo: document.body,
    })
    const sectionEl = wrapper.find('#section-1').element
    const scrollIntoView = vi.fn()
    sectionEl.scrollIntoView = scrollIntoView

    await wrapper.setProps({ selectedSectionId: '1' })
    await flushPromises()
    await flushPromises()

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
  })
})
