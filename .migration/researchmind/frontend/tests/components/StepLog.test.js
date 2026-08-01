/**
 * StepLog 组件测试
 *
 * - 日志追加
 * - 图标颜色
 * - 自动滚动
 * - sticky「最新」按钮
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import StepLog from '@/components/task/StepLog.vue'

function mountLog(props = {}) {
  return mount(StepLog, {
    props: {
      logs: [],
      sseStatus: 'connected',
      ...props,
    },
    global: { plugins: [createPinia()] },
    attachTo: document.body,
  })
}

describe('StepLog', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
  })

  it('空日志显示等待提示', () => {
    const wrapper = mountLog()
    expect(wrapper.text()).toContain('等待任务开始')
  })

  it('渲染日志条目_含时间与消息', () => {
    const wrapper = mountLog({
      logs: [
        { id: 'l1', type: 'system', icon: 'fa-play', level: 'info', message: '任务已创建', timestamp: '2026-06-24T10:00:00Z' },
      ],
    })
    expect(wrapper.text()).toContain('任务已创建')
  })

  it('不同 level 应用对应颜色类', () => {
    const wrapper = mountLog({
      logs: [
        { id: 'l1', type: 'system', icon: 'fa-check', level: 'success', message: '完成', timestamp: '2026-06-24T10:00:00Z' },
        { id: 'l2', type: 'system', icon: 'fa-ban', level: 'error', message: '失败', timestamp: '2026-06-24T10:00:01Z' },
      ],
    })
    const lines = wrapper.findAll('.terminal-log-line')
    expect(lines[0].classes()).toContain('log-success')
    expect(lines[1].classes()).toContain('log-error')
  })

  it('连接中显示 LIVE 状态', () => {
    const wrapper = mountLog({ sseStatus: 'connected' })
    expect(wrapper.text()).toContain('LIVE')
  })

  it('日志面板无内部滚动_内容由外层容器统一滚动', () => {
    const wrapper = mountLog({
      logs: Array.from({ length: 30 }, (_, i) => ({
        id: `l${i}`,
        type: 'system',
        icon: 'fa-info',
        level: 'info',
        message: `日志 ${i}`,
        timestamp: '2026-06-24T10:00:00Z',
      })),
    })
    // 不再有内部滚动按钮
    expect(wrapper.find('.scroll-to-bottom').exists()).toBe(false)
  })

  it('step 日志优先使用 message 字段渲染', () => {
    const wrapper = mountLog({
      logs: [
        {
          id: 'l1',
          type: 'step',
          icon: 'fa-spinner',
          level: 'info',
          status: 'running',
          message: '步骤消息',
          label: '步骤标签',
          stepType: 'search',
          timestamp: '2026-06-24T10:00:00Z',
        },
      ],
    })
    expect(wrapper.text()).toContain('步骤消息')
  })

  it('message 为空时 fallback 到 label', () => {
    const wrapper = mountLog({
      logs: [
        {
          id: 'l1',
          type: 'step',
          icon: 'fa-spinner',
          level: 'info',
          status: 'running',
          message: '',
          label: '步骤标签',
          stepType: 'search',
          timestamp: '2026-06-24T10:00:00Z',
        },
      ],
    })
    expect(wrapper.text()).toContain('步骤标签')
  })

  it('message 与 label 均为空时 fallback 到 stepType', () => {
    const wrapper = mountLog({
      logs: [
        {
          id: 'l1',
          type: 'step',
          icon: 'fa-spinner',
          level: 'info',
          status: 'running',
          message: '',
          label: '',
          stepType: 'fetch',
          timestamp: '2026-06-24T10:00:00Z',
        },
      ],
    })
    expect(wrapper.text()).toContain('fetch')
  })

  it('step.progress.label 与日志 message 同时显示', () => {
    const wrapper = mountLog({
      logs: [
        {
          id: 'l1',
          type: 'step',
          icon: 'fa-spinner',
          level: 'info',
          status: 'running',
          message: '综合',
          timestamp: '2026-06-24T10:00:00Z',
          progress: { label: '正在对 8 条来源进行跨源综合...' },
        },
      ],
    })
    expect(wrapper.text()).toContain('综合')
    expect(wrapper.text()).toContain('正在对 8 条来源进行跨源综合...')
  })
})
