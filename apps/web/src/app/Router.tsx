import { createBrowserRouter } from 'react-router-dom'

function BaselinePage() {
  return (
    <main className="baseline" aria-labelledby="baseline-title">
      <p className="baseline__eyebrow">据见 · Evidence workspace</p>
      <h1 id="baseline-title">EvidSight</h1>
      <p>没有凭据，不立结论。</p>
    </main>
  )
}

export const router = createBrowserRouter([
  {
    path: '*',
    element: <BaselinePage />,
  },
])
