/**
 * TypeCard 组件测试 — 覆盖 src/components/task/TypeCard.vue
 *
 * 对齐 ROADMAP.md §3.9：
 *   - 三卡渲染（comparison / explainer / analysis）
 *   - 点击选中（border-teal-600 + bg-teal-50）
 *   - 三选一互斥（通过父组件 selected prop 控制）
 *   - 再次点击取消（emit select 同 type）
 *   - 选中勾标 icon 显示/隐藏
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TypeCard from '@/components/task/TypeCard.vue'

describe('TypeCard', () => {
  // ===== 渲染 =====

  it('渲染 comparison 类型卡片_含图标和标题', () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'comparison', selected: false },
    })

    expect(wrapper.find('.type-card').exists()).toBe(true)
    expect(wrapper.find('.type-title').text()).toBe('对比型研究')
    expect(wrapper.find('.type-desc').text()).toContain('结构化对比')
    expect(wrapper.find('.type-example').text()).toContain('向量数据库')
    expect(wrapper.find('.fa-balance-scale').exists()).toBe(true)
  })

  it('渲染 explainer 类型卡片_含图标和标题', () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'explainer', selected: false },
    })

    expect(wrapper.find('.type-title').text()).toBe('解释型研究')
    expect(wrapper.find('.type-desc').text()).toContain('观点聚类')
    expect(wrapper.find('.type-example').text()).toContain('Transformer')
    expect(wrapper.find('.fa-lightbulb').exists()).toBe(true)
  })

  it('渲染 analysis 类型卡片_含图标和标题', () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'analysis', selected: false },
    })

    expect(wrapper.find('.type-title').text()).toBe('影响分析型')
    expect(wrapper.find('.type-desc').text()).toContain('因果推理')
    expect(wrapper.find('.type-example').text()).toContain('量子计算')
    expect(wrapper.find('.fa-chart-line').exists()).toBe(true)
  })

  // ===== 选中态视觉 =====

  it('selected=true 应用 selected class', () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'comparison', selected: true },
    })

    expect(wrapper.find('.type-card').classes()).toContain('selected')
  })

  it('selected=false 不应用 selected class', () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'comparison', selected: false },
    })

    expect(wrapper.find('.type-card').classes()).not.toContain('selected')
  })

  it('selected=true 显示选中勾标 icon', () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'comparison', selected: true },
    })

    expect(wrapper.find('.fa-circle-check.check-icon').exists()).toBe(true)
  })

  it('selected=false 不显示选中勾标 icon', () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'explainer', selected: false },
    })

    expect(wrapper.find('.fa-circle-check.check-icon').exists()).toBe(false)
  })

  // ===== 交互：点击 emit select =====

  it('点击卡片_emit select 事件携带 type 值', async () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'comparison', selected: false },
    })

    await wrapper.find('.type-card').trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')[0]).toEqual(['comparison'])
  })

  it('点击 explainer 卡片_emit explainer', async () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'explainer', selected: false },
    })

    await wrapper.find('.type-card').trigger('click')
    expect(wrapper.emitted('select')[0]).toEqual(['explainer'])
  })

  it('点击 analysis 卡片_emit analysis', async () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'analysis', selected: false },
    })

    await wrapper.find('.type-card').trigger('click')
    expect(wrapper.emitted('select')[0]).toEqual(['analysis'])
  })

  it('selected 为 true 时再次点击_仍然 emit select（取消由父组件处理）', async () => {
    const wrapper = mount(TypeCard, {
      props: { type: 'comparison', selected: true },
    })

    await wrapper.find('.type-card').trigger('click')
    // 仍 emit，父组件收到后可将 selected 设为 false
    expect(wrapper.emitted('select')[0]).toEqual(['comparison'])
  })

  // ===== 三选一互斥（由父组件实现） =====

  it('父组件通过 selected prop 控制三选一互斥', () => {
    // 模拟 ResearchPage 的功能：三张卡片同时渲染，仅一张 selected
    const cards = ['comparison', 'explainer', 'analysis'].map((type) =>
      mount(TypeCard, {
        props: { type, selected: type === 'comparison' },
      })
    )

    expect(cards[0].find('.type-card').classes()).toContain('selected')
    expect(cards[1].find('.type-card').classes()).not.toContain('selected')
    expect(cards[2].find('.type-card').classes()).not.toContain('selected')
  })

  // ===== Props 校验 =====

  it('非法 type 值_控制台警告但不崩溃', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mount(TypeCard, {
      props: { type: 'invalid_type', selected: false },
    })
    // Vue validator 应触发警告
    expect(spy).toHaveBeenCalled()
    spy.mockRestore()
  })
})
