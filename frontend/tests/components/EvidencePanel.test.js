/**
 * EvidencePanel 组件测试
 *
 * - 按 index 排序
 * - 点击 emit select
 * - 按章节筛选
 * - flash 高亮
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import EvidencePanel from '@/components/report/EvidencePanel.vue'

function mountPanel(props = {}) {
  return mount(EvidencePanel, {
    props: {
      evidence: [
        { index: 1, sourceId: 2, sourceUrl: 'https://example.com/b', sourceTitle: 'Example B', domain: 'example.com', content: 'B', relevanceScore: 0.8, usedInSections: ['1'] },
        { index: 0, sourceId: 1, sourceUrl: 'https://nist.gov/a', sourceTitle: 'NIST A', domain: 'nist.gov', content: 'A', relevanceScore: 0.9, usedInSections: ['0'] },
      ],
      highlightedIndex: null,
      filterSectionId: null,
      ...props,
    },
    global: { plugins: [createPinia()] },
  })
}

describe('EvidencePanel', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('按 index 升序渲染卡片，展示索引从 1 开始', () => {
    const wrapper = mountPanel()
    const cards = wrapper.findAll('.evidence-card')
    expect(cards[0].attributes('data-evidence-index')).toBe('0')
    expect(cards[1].attributes('data-evidence-index')).toBe('1')
    expect(cards[0].find('.evidence-tag').text()).toBe('来源1')
    expect(cards[1].find('.evidence-tag').text()).toBe('来源2')
  })

  it('点击卡片 emit select 事件', async () => {
    const wrapper = mountPanel()
    await wrapper.findAll('.evidence-card')[0].trigger('click')
    expect(wrapper.emitted('select')).toHaveLength(1)
    expect(wrapper.emitted('select')[0]).toEqual([0])
  })

  it('高亮索引对应卡片带 flash 类', () => {
    const wrapper = mountPanel({ highlightedIndex: 1 })
    const cards = wrapper.findAll('.evidence-card')
    expect(cards[1].classes()).toContain('flash')
    expect(cards[0].classes()).not.toContain('flash')
  })

  it('点击章节 badge emit filter 事件', async () => {
    const wrapper = mountPanel()
    const badge = wrapper.find('.evidence-section-badge')
    await badge.trigger('click')
    expect(wrapper.emitted('filter')).toHaveLength(1)
    expect(wrapper.emitted('filter')[0]).toEqual(['0'])
  })

  it('渲染可点击的来源链接', () => {
    const wrapper = mountPanel()
    const link = wrapper.find('.evidence-source')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://nist.gov/a')
    expect(link.text()).toContain('NIST A')
  })

  it('来源链接点击不触发卡片 select', async () => {
    const wrapper = mountPanel()
    const link = wrapper.find('.evidence-source')
    await link.trigger('click')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('证据卡片宽度占满并防止溢出', () => {
    const wrapper = mountPanel()
    const card = wrapper.find('.evidence-card')
    const style = window.getComputedStyle(card.element)

    expect(style.width).toBe('100%')
    expect(style.minWidth).toBe('0')
    expect(style.overflow).toBe('hidden')
  })

  it('证据内容使用 5 行截断与自动换行', () => {
    const wrapper = mountPanel()
    const content = wrapper.find('.evidence-content')
    const style = window.getComputedStyle(content.element)

    expect(style.webkitLineClamp).toBe('5')
    expect(style.overflowWrap).toBe('break-word')
  })
})
