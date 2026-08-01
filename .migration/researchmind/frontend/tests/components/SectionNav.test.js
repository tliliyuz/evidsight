/**
 * SectionNav 组件测试
 *
 * - 渲染章节列表
 * - 当前高亮
 * - 点击 emit select
 * - badge 引用计数
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SectionNav from '@/components/report/SectionNav.vue'

function mountNav(props = {}) {
  return mount(SectionNav, {
    props: {
      sections: [
        { id: '0', heading: '1. 概述', content: '', sources: [] },
        { id: '1', heading: '2. 方案', content: '', sources: [] },
      ],
      activeId: '0',
      evidence: [],
      ...props,
    },
    global: { plugins: [createPinia()] },
  })
}

describe('SectionNav', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('渲染章节列表', () => {
    const wrapper = mountNav()
    const items = wrapper.findAll('.section-nav-item')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('1. 概述')
  })

  it('当前章节带 active 类', () => {
    const wrapper = mountNav({ activeId: '1' })
    const items = wrapper.findAll('.section-nav-item')
    expect(items[1].classes()).toContain('active')
    expect(items[0].classes()).not.toContain('active')
  })

  it('点击章节 emit select 事件', async () => {
    const wrapper = mountNav()
    await wrapper.findAll('.section-nav-item')[1].trigger('click')
    expect(wrapper.emitted('select')).toHaveLength(1)
    expect(wrapper.emitted('select')[0]).toEqual(['1'])
  })

  it('章节引用计数 badge 正确', () => {
    const wrapper = mountNav({
      evidence: [
        { index: 0, usedInSections: ['0'] },
        { index: 1, usedInSections: ['0', '1'] },
      ],
    })
    const badges = wrapper.findAll('.section-citation-count')
    expect(badges[0].text()).toBe('2')
    expect(badges[1].text()).toBe('1')
  })

  it('标题、条目、badge 字体大小使用 CSS 变量', () => {
    const wrapper = mountNav({
      evidence: [{ index: 0, usedInSections: ['0'] }],
    })
    const title = wrapper.find('.section-nav-title')
    const item = wrapper.find('.section-nav-item')
    const badge = wrapper.find('.section-citation-count')

    expect(window.getComputedStyle(title.element).fontSize).toContain('--rm-text-xs')
    expect(window.getComputedStyle(item.element).fontSize).toContain('--rm-text-sm')
    expect(window.getComputedStyle(badge.element).fontSize).toContain('--rm-text-xs')
  })

  it('章节导航容器 padding 使用 CSS 变量', () => {
    const wrapper = mountNav()
    const nav = wrapper.find('.section-nav')
    const padding = window.getComputedStyle(nav.element).padding

    expect(padding).toContain('--rm-space-2')
    expect(padding).toContain('--rm-space-1_5')
  })
})
