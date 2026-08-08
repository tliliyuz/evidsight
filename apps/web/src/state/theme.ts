export type Theme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'evidsight-theme'

export function initializeTheme(): Theme {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  const theme: Theme = stored === 'dark' ? 'dark' : 'light'
  document.documentElement.dataset.theme = theme
  return theme
}

export function setTheme(theme: Theme): void {
  localStorage.setItem(THEME_STORAGE_KEY, theme)
  document.documentElement.dataset.theme = theme
}
