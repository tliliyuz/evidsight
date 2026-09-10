import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from '@/app/App'
import '@/styles/global.css'

const root = document.getElementById('root')

if (!root) {
  throw new Error('缺少 React 根节点 #root')
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
