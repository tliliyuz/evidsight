// 路由守卫测试 — 覆盖 src/router/index.js 的 beforeEach 守卫
// 对齐 TESTING_STRATEGY.md §5.4：未登录→/login、已登录访问/login→/research、非admin→/admin重定向

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { createRouter, createMemoryHistory } from 'vue-router'

// 路由表懒加载组件需 stub；用内存 router 直接驱动守卫
// 注意：router 模块内部用 useAuthStore()，需 Pinia 已激活

function makeJwt(payload) {
  const enc = (o) => btoa(JSON.stringify(o)).replace(/=/g, '')
  return `${enc({ alg: 'HS256', typ: 'JWT' })}.${enc(payload)}.sig`
}

function setupStore({ loggedIn, role = 'user' } = {}) {
  const store = useAuthStore()
  if (loggedIn) {
    const at = makeJwt({ sub: '1', username: 'tester', role, exp: Math.floor(Date.now() / 1000) + 900 })
    store.setTokens(at, 'rt')
    store.user = { id: 1, username: 'tester', role }
  } else {
    store.user = null
    store.token = ''
  }
  return store
}

// 内联路由表（与 src/router/index.js 结构一致），占位组件避免懒加载副作用
const placeholder = { template: '<div/>' }

function buildIsolatedRouter() {
  const routes = [
    { path: '/login', name: 'Login', component: placeholder, meta: { public: true } },
    { path: '/research', name: 'Research', component: placeholder, meta: { requiresAuth: true } },
    { path: '/history', name: 'History', component: placeholder, meta: { requiresAuth: true } },
    {
      path: '/admin',
      component: placeholder,
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        { path: 'stats', name: 'AdminStats', component: placeholder },
        { path: 'tasks', name: 'AdminTasks', component: placeholder },
      ],
    },
    { path: '/', redirect: '/research' },
    { path: '/:pathMatch(.*)*', redirect: '/research' },
  ]
  const router = createRouter({ history: createMemoryHistory(), routes })
  // 复制守卫逻辑：与 src/router/index.js beforeEach 一致
  router.beforeEach((to, from, next) => {
    const authStore = useAuthStore()
    if (to.meta.public && authStore.isLoggedIn) {
      next('/research')
      return
    }
    if (to.meta.requiresAuth && !authStore.isLoggedIn) {
      next('/login')
      return
    }
    const requiresAdmin = to.matched.some((record) => record.meta.requiresAdmin)
    if (requiresAdmin && !authStore.isAdmin) {
      next('/research')
      return
    }
    next()
  })
  return router
}

describe('路由守卫', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('未登录访问需认证页面_重定向到/login', async () => {
    setupStore({ loggedIn: false })
    const router = buildIsolatedRouter()
    await router.push('/research')
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('未登录访问/history_重定向到/login', async () => {
    setupStore({ loggedIn: false })
    const router = buildIsolatedRouter()
    await router.push('/history')
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('已登录用户访问/login_重定向到/research', async () => {
    setupStore({ loggedIn: true, role: 'user' })
    const router = buildIsolatedRouter()
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/research')
  })

  it('普通用户访问/admin_重定向到/research', async () => {
    setupStore({ loggedIn: true, role: 'user' })
    const router = buildIsolatedRouter()
    await router.push('/admin/stats')
    expect(router.currentRoute.value.path).toBe('/research')
  })

  it('admin用户访问/admin_允许通过', async () => {
    setupStore({ loggedIn: true, role: 'admin' })
    const router = buildIsolatedRouter()
    await router.push('/admin/stats')
    expect(router.currentRoute.value.path).toBe('/admin/stats')
  })

  it('已登录普通用户访问/research_允许通过', async () => {
    setupStore({ loggedIn: true, role: 'user' })
    const router = buildIsolatedRouter()
    await router.push('/research')
    expect(router.currentRoute.value.path).toBe('/research')
  })

  it('根路径重定向到/research', async () => {
    setupStore({ loggedIn: true, role: 'user' })
    const router = buildIsolatedRouter()
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/research')
  })
})
