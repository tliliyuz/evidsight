/**
 * PipelineProgress 组件测试
 *
 * - 7 个阶段节点渲染
 * - done/current/pending 状态类名
 * - 进度条宽度
 * - 阶段耗时显示
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PipelineProgress from '@/components/task/PipelineProgress.vue'
import { initPhaseStates } from '@/utils/phase'

function mountProgress(props = {}) {
  return mount(PipelineProgress, {
    props: {
      phases: initPhaseStates(),
      progress: { completed_steps: 0, total_steps: 10, progress: 0 },
      phaseDurations: {},
      ...props,
    },
    global: { plugins: [createPinia()] },
  })
}

describe('PipelineProgress', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('渲染 7 个阶段节点', () => {
    const wrapper = mountProgress()
    const nodes = wrapper.findAll('.phase-node')
    expect(nodes).toHaveLength(7)
  })

  it('当前阶段节点带 current 类并旋转', () => {
    const phases = initPhaseStates()
    phases.search = 'running'
    const wrapper = mountProgress({ phases })

    const searchNode = wrapper.findAll('.phase-node')[1]
    expect(searchNode.classes()).toContain('current')
    expect(searchNode.find('i').classes()).toContain('fa-spin')
  })

  it('已完成阶段带 done 类', () => {
    const phases = initPhaseStates()
    phases.planning = 'done'
    const wrapper = mountProgress({ phases })

    const planningNode = wrapper.findAll('.phase-node')[0]
    expect(planningNode.classes()).toContain('done')
  })

  it('未开始阶段带 pending 类', () => {
    const wrapper = mountProgress()

    const renderNode = wrapper.findAll('.phase-node')[6]
    expect(renderNode.classes()).toContain('pending')
  })

  it('进度条宽度与 progress 字段一致', () => {
    const wrapper = mountProgress({ progress: { completed_steps: 5, total_steps: 10, progress: 0.5 } })
    const fill = wrapper.find('.pipeline-progress-fill')
    expect(fill.attributes('style')).toContain('width: 50%')
  })

  it('阶段耗时显示在节点下方', () => {
    const wrapper = mountProgress({ phaseDurations: { planning: 1200 } })
    expect(wrapper.text()).toContain('任务规划')
    expect(wrapper.text()).toContain('1.2s')
  })

  it('Planning 阶段显示任务规划中且不显示步骤数', () => {
    const phases = initPhaseStates()
    phases.planning = 'running'
    const wrapper = mountProgress({
      phases,
      progress: { completed_steps: 0, total_steps: 0, progress: 0 },
    })
    expect(wrapper.text()).toContain('任务规划中…')
    expect(wrapper.text()).not.toContain('0/0')
  })

  it('Planning 完成后显示百分比与步骤数', () => {
    const phases = initPhaseStates()
    phases.planning = 'done'
    phases.search = 'running'
    const wrapper = mountProgress({
      phases,
      progress: { completed_steps: 3, total_steps: 10, progress: 0.3 },
    })
    expect(wrapper.text()).toContain('30%')
    expect(wrapper.text()).toContain('3/7')
  })

  it('分母固定为七阶段：总步骤增长不影响分母显示', async () => {
    const phases = initPhaseStates()
    phases.planning = 'done'
    phases.search = 'running'
    const wrapper = mountProgress({
      phases,
      progress: { completed_steps: 3, total_steps: 3, progress: 1 },
    })
    expect(wrapper.text()).toContain('3/7')

    await wrapper.setProps({
      progress: { completed_steps: 3, total_steps: 30, progress: 0.1 },
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('3/7')
    expect(wrapper.text()).not.toContain('3/30')
  })
})
