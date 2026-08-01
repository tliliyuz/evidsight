/**
 * CanceledView 组件测试
 *
 * - 显示已取消状态与主题
 * - 显示已完成阶段摘要
 * - 点击返回 emit back
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CanceledView from '@/components/report/CanceledView.vue'
import { initPhaseStates } from '@/utils/phase'

describe('CanceledView', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('显示取消状态与主题', () => {
    const wrapper = mount(CanceledView, {
      props: { topic: '测试主题', phases: initPhaseStates(), phaseDurations: {} },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('研究已取消')
    expect(wrapper.text()).toContain('测试主题')
  })

  it('取消卡片为固定宽度且按钮固定在底部', () => {
    const wrapper = mount(CanceledView, {
      props: { topic: '测试主题', phases: initPhaseStates(), phaseDurations: {} },
      global: { plugins: [createPinia()] },
    })
    const card = wrapper.find('.canceled-card')
    const footer = wrapper.find('.card-footer')
    expect(window.getComputedStyle(card.element).width).toBe('560px')
    expect(footer.exists()).toBe(true)
    expect(footer.find('.back-btn').exists()).toBe(true)
  })

  it('显示已完成阶段摘要', () => {
    const phases = initPhaseStates()
    phases.planning = 'done'
    phases.search = 'done'
    const wrapper = mount(CanceledView, {
      props: {
        topic: '测试主题',
        phases,
        phaseDurations: { planning: 1200, search: 3500 },
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('任务规划')
    expect(wrapper.text()).toContain('搜索')
    expect(wrapper.text()).toContain('1.2s')
  })

  it('点击返回 emit back', async () => {
    const wrapper = mount(CanceledView, {
      props: { topic: '测试主题', phases: initPhaseStates(), phaseDurations: {} },
      global: { plugins: [createPinia()] },
    })
    await wrapper.find('.back-btn').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})
