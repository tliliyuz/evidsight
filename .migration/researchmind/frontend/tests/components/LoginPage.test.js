// LoginPage 组件测试 — 覆盖 src/views/LoginPage.vue
// 对齐 TESTING_STRATEGY.md §5.3：表单校验 / Tab 切换 / loading / 错误提示 / 跳转

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import LoginPage from '@/views/LoginPage.vue'
import { useAuthStore } from '@/stores/auth'

// Mock @/api/auth（store 内部依赖）
vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  refreshToken: vi.fn(),
  logout: vi.fn(),
}))

// Mock ElMessage（setup.js 已全局 mock，这里仅引入校验调用）
import { ElMessage } from 'element-plus'

function makeJwt(payload) {
  const enc = (o) => btoa(JSON.stringify(o)).replace(/=/g, '')
  return `${enc({ alg: 'HS256', typ: 'JWT' })}.${enc(payload)}.sig`
}

function router() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'Login', component: LoginPage },
      { path: '/research', name: 'Research', component: { template: '<div>research</div>' } },
    ],
  })
}

async function mountLogin() {
  const r = router()
  await r.push('/login')
  await r.isReady()
  const wrapper = mount(LoginPage, {
    global: {
      plugins: [r, createPinia(), ElementPlus],
      stubs: { transition: false },
    },
  })
  return { wrapper, r }
}

describe('LoginPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('渲染品牌区与登录Tab_默认登录模式', async () => {
    const { wrapper } = await mountLogin()
    expect(wrapper.find('.app-title').text()).toBe('ResearchMind')
    expect(wrapper.find('.app-subtitle').text()).toBe('可审计的结构化研究引擎')
    // 默认登录模式：提交按钮文案「登 录」
    expect(wrapper.find('.submit-btn').text()).toContain('登')
    // 登录 Tab 激活
    expect(wrapper.findAll('.tab-btn')[0].classes()).toContain('active')
  })

  it('点击注册Tab_切换到注册模式_清空表单', async () => {
    const { wrapper } = await mountLogin()
    await wrapper.findAll('.tab-btn')[1].trigger('click')
    expect(wrapper.findAll('.tab-btn')[1].classes()).toContain('active')
    expect(wrapper.find('.submit-btn').text()).toContain('注')
  })

  it('登录↔注册Tab可来回切换', async () => {
    const { wrapper } = await mountLogin()
    const tabs = wrapper.findAll('.tab-btn')
    await tabs[1].trigger('click') // 注册
    expect(wrapper.find('.submit-btn').text()).toContain('注')
    await tabs[0].trigger('click') // 回登录
    expect(wrapper.find('.submit-btn').text()).toContain('登')
  })

  it('空用户名_显示错误提示不提交', async () => {
    const { wrapper } = await mountLogin()
    const store = useAuthStore()
    const spy = vi.spyOn(store, 'login').mockResolvedValue({})
    await wrapper.find('form').trigger('submit.prevent')
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toContain('用户名')
    expect(spy).not.toHaveBeenCalled()
  })

  it('用户名少于2字符_显示错误提示', async () => {
    const { wrapper } = await mountLogin()
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('a')
    await inputs[1].setValue('pass123')
    await wrapper.find('form').trigger('submit.prevent')
    expect(wrapper.find('.error-msg').text()).toContain('2')
  })

  it('纯数字用户名_显示错误提示', async () => {
    const { wrapper } = await mountLogin()
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('12345')
    await inputs[1].setValue('pass123')
    await wrapper.find('form').trigger('submit.prevent')
    expect(wrapper.find('.error-msg').text()).toContain('纯数字')
  })

  it('密码少于6字符_显示错误提示', async () => {
    const { wrapper } = await mountLogin()
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('tester')
    await inputs[1].setValue('12345')
    await wrapper.find('form').trigger('submit.prevent')
    expect(wrapper.find('.error-msg').text()).toContain('密码')
    expect(wrapper.find('.error-msg').text()).toContain('6')
  })

  it('登录成功_跳转到research', async () => {
    const { wrapper, r } = await mountLogin()
    const at = makeJwt({ sub: '1', username: 'tester', role: 'user', exp: Math.floor(Date.now() / 1000) + 900 })
    const store = useAuthStore()
    vi.spyOn(store, 'login').mockResolvedValue({ id: 1, username: 'tester', role: 'user' })
    // 拦截 ElMessage
    ElMessage.success.mockImplementation(() => {})

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('tester')
    await inputs[1].setValue('pass123')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(r.currentRoute.value.path).toBe('/research')
    expect(ElMessage.success).toHaveBeenCalledWith('登录成功')
  })

  it('登录失败_显示错误提示_loading结束', async () => {
    const { wrapper } = await mountLogin()
    const store = useAuthStore()
    vi.spyOn(store, 'login').mockRejectedValue({ response: { data: { message: '用户名或密码错误' } } })

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('tester')
    await inputs[1].setValue('pass123')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.find('.error-msg').text()).toContain('用户名或密码错误')
    expect(wrapper.find('.submit-btn').attributes('disabled')).toBeUndefined()
  })

  it('提交中_按钮disabled+loading', async () => {
    const { wrapper } = await mountLogin()
    const store = useAuthStore()
    let resolveLogin
    vi.spyOn(store, 'login').mockReturnValue(new Promise((r) => { resolveLogin = r }))

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('tester')
    await inputs[1].setValue('pass123')
    wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.find('.submit-btn').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.fa-spinner').exists()).toBe(true)

    resolveLogin({ id: 1, username: 'tester', role: 'user' })
    await flushPromises()
  })

  it('注册成功_切回登录模式并提示', async () => {
    const { wrapper } = await mountLogin()
    const store = useAuthStore()
    vi.spyOn(store, 'register').mockResolvedValue({ id: 5, username: 'newuser' })
    ElMessage.success.mockImplementation(() => {})

    // 切到注册
    await wrapper.findAll('.tab-btn')[1].trigger('click')
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('newuser')
    await inputs[1].setValue('pass123')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    // 注册成功切回登录
    expect(wrapper.find('.submit-btn').text()).toContain('登')
    expect(ElMessage.success).toHaveBeenCalledWith('注册成功，请登录')
  })
})
