/**
 * TracePanel 组件测试
 *
 * - 阶段耗时显示
 * - 总耗时计算
 * - 折叠展开
 * - 字段名对齐后端 TraceRecorder 输出
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TracePanel from '@/components/report/TracePanel.vue'

describe('TracePanel', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('渲染各阶段耗时与详情', () => {
    const wrapper = mount(TracePanel, {
      props: {
        trace: {
          planning: { duration_ms: 1200 },
          search: { total_results: 45, success_count: 10, skipped_count: 2, duration_ms: 3500 },
        },
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('任务规划')
    expect(wrapper.text()).toContain('搜索')
    expect(wrapper.text()).toContain('1.2s')
    expect(wrapper.text()).toContain('10/45')
  })

  it('搜索阶段显示 success_count/total_results', () => {
    const wrapper = mount(TracePanel, {
      props: {
        trace: {
          search: { total_results: 80, success_count: 60, skipped_count: 5, duration_ms: 2000 },
        },
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('60/80')
  })

  it('抓取阶段显示 success_count/total_urls', () => {
    const wrapper = mount(TracePanel, {
      props: {
        trace: {
          fetch: { total_urls: 40, success_count: 35, skipped_count: 3, duration_ms: 2500 },
        },
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('35/40')
  })

  it('重排阶段显示 bm25_candidates→llm_reranked', () => {
    const wrapper = mount(TracePanel, {
      props: {
        trace: {
          rerank: { bm25_candidates: 30, llm_reranked: 8, duration_ms: 1800 },
        },
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('30→8')
  })

  it('来源图谱阶段显示 evidence_count', () => {
    const wrapper = mount(TracePanel, {
      props: {
        trace: {
          evidence_graph: { evidence_count: 12, source_count: 8, duration_ms: 900 },
        },
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('12')
  })

  it('渲染阶段显示 sections_count/citations_count', () => {
    const wrapper = mount(TracePanel, {
      props: {
        trace: {
          render: { sections_count: 5, citations_count: 16, duration_ms: 600 },
        },
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('5/16')
  })

  it('为各阶段渲染耗时比例进度条', async () => {
    const wrapper = mount(TracePanel, {
      props: {
        trace: {
          planning: { duration_ms: 1000 },
          search: { total_results: 10, success_count: 8, duration_ms: 3000 },
        },
      },
      global: { plugins: [createPinia()] },
    })
    await wrapper.find('.trace-header').trigger('click')
    const bars = wrapper.findAll('.stage-bar')
    expect(bars.length).toBe(7)
    expect(bars[0].attributes('style')).toContain('width: 25%')
    expect(bars[1].attributes('style')).toContain('width: 75%')
    expect(bars[2].attributes('style')).toContain('width: 0%')
  })

  it('计算并显示总耗时', () => {
    const wrapper = mount(TracePanel, {
      props: {
        trace: {
          planning: { duration_ms: 1000 },
          search: { total_results: 10, success_count: 8, duration_ms: 2000 },
        },
      },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.text()).toContain('总计')
    expect(wrapper.text()).toContain('3.0s')
  })

  it('默认折叠_点击展开', async () => {
    const wrapper = mount(TracePanel, {
      props: { trace: { planning: { duration_ms: 1000 } } },
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.find('.trace-body').attributes('style')).toContain('display: none')
    await wrapper.find('.trace-header').trigger('click')
    expect(wrapper.find('.trace-body').attributes('style')).toBe('')
  })
})
