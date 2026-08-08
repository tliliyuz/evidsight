import { describe, expect, it } from 'vitest'

import { initializeTheme, setTheme } from '@/state/theme'

describe('主题偏好', () => {
  it('切换后写入 evidsight-theme 并可在刷新时恢复', () => {
    setTheme('dark')
    document.documentElement.dataset.theme = 'light'

    expect(initializeTheme()).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('evidsight-theme')).toBe('dark')
  })
})
