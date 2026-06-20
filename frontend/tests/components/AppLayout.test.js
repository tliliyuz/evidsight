// AppLayout 组件测试 — 覆盖 src/components/layout/AppLayout.vue
// 对齐 TESTING_STRATEGY.md §5.3：布局渲染 / Sidebar 存在性 / <slot /> 内容区

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import AppLayout from '@/components/layout/AppLayout.vue'

// Sidebar 依赖 authStore + router，使用真实组件以验证集成
function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/research', name: 'Research', component: { template: '<div>research</div>' } },
      { path: '/history', name: 'History', component: { template: '<div>history</div>' } },
    ],
  })
}

async function mountLayout(routeName = 'Research') {
  const r = makeRouter()
  await r.push({ name: routeName })
  await r.isReady()
  const wrapper = mount(AppLayout, {
    global: {
      plugins: [r, createPinia(), ElementPlus],
      stubs: { transition: false },
    },
    slots: {
      default: '<div class="slot-content">主内容区</div>',
    },
  })
  return { wrapper, r }
}

describe('AppLayout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('渲染整体布局_包含app-layout容器', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.find('.app-layout').exists()).toBe(true)
    expect(wrapper.find('.main-area').exists()).toBe(true)
  })

  it('渲染Sidebar组件', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.findComponent({ name: 'Sidebar' }).exists()).toBe(true)
    // Sidebar 根节点 class
    expect(wrapper.find('.sidebar').exists()).toBe(true)
  })

  it('slot内容渲染到主内容区', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.find('.content-scroll .slot-content').exists()).toBe(true)
    expect(wrapper.find('.slot-content').text()).toBe('主内容区')
  })

  it('顶部Header渲染_Research路由标题为ResearchMind', async () => {
    const { wrapper } = await mountLayout('Research')
    expect(wrapper.find('.top-header').exists()).toBe(true)
    expect(wrapper.find('.page-title').text()).toBe('ResearchMind')
  })

  it('History路由_页面标题为历史任务', async () => {
    const { wrapper } = await mountLayout('History')
    expect(wrapper.find('.page-title').text()).toBe('历史任务')
  })
})
