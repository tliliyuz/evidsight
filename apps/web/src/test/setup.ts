import '@testing-library/jest-dom/vitest'

afterEach(() => {
  localStorage.clear()
  document.documentElement.dataset.theme = 'light'
})
