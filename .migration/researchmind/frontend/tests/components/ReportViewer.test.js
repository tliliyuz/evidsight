/**
 * ReportViewer 组件测试
 *
 * - 进入完成态自动加载报告
 * - 加载态渲染骨架屏 + spinning
 * - 加载完成后渲染报告正文与 Evidence 面板
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import ReportViewer from '@/components/report/ReportViewer.vue'
import { useReportStore } from '@/stores/report'

vi.mock('@/api/research', () => ({
  getReport: vi.fn(),
}))

import * as researchApi from '@/api/research'

describe('ReportViewer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  function mountViewer(task = makeTask()) {
    return mount(ReportViewer, {
      props: { task },
      global: { plugins: [createPinia()] },
    })
  }

  function makeTask(overrides = {}) {
    return {
      task_id: 'task-1',
      topic: '量子计算',
      status: 'completed',
      total_sources: 3,
      total_evidence: 2,
      completed_at: '2026-06-26T10:00:00Z',
      ...overrides,
    }
  }

  it('进入完成态时自动调用 getReport', async () => {
    researchApi.getReport.mockResolvedValue({
      data: {
        data: {
          report: { title: '量子计算报告', sections: [] },
          evidence_graph: { items: [] },
          trace: null,
        },
      },
    })
    mountViewer()
    await flushPromises()
    expect(researchApi.getReport).toHaveBeenCalledWith('task-1')
  })

  it('加载态显示骨架屏与 spinning', async () => {
    let resolveReport
    const promise = new Promise(resolve => { resolveReport = resolve })
    researchApi.getReport.mockReturnValue(promise)

    const wrapper = mountViewer()
    await nextTick()

    expect(wrapper.find('.section-nav-skeleton').exists()).toBe(true)
    expect(wrapper.find('.report-article-loading').exists()).toBe(true)
    expect(wrapper.find('.report-side-panel-skeleton').exists()).toBe(true)
    expect(wrapper.find('.fa-spinner.fa-spin').exists()).toBe(true)

    resolveReport({
      data: {
        data: {
          report: { title: '量子计算报告', sections: [] },
          evidence_graph: { items: [] },
          trace: null,
        },
      },
    })
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.section-nav-skeleton').exists()).toBe(false)
    expect(wrapper.find('.report-article-loading').exists()).toBe(false)
  })

  it('加载完成后渲染报告标题与章节导航', async () => {
    researchApi.getReport.mockResolvedValue({
      data: {
        data: {
          report: {
            title: '量子计算报告',
            sections: [
              { heading: '概述', content: '这是概述。' },
              { heading: '技术路线', content: '这是技术路线。' },
            ],
          },
          evidence_graph: { items: [] },
          trace: null,
        },
      },
    })
    const wrapper = mountViewer()
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.report-title').text()).toBe('量子计算报告')
    expect(wrapper.text()).toContain('概述')
    expect(wrapper.text()).toContain('技术路线')
  })
})
