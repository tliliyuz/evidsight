import { useSyncExternalStore } from 'react'
import { createBrowserRouter, Outlet } from 'react-router-dom'

import { AppShell } from '@/app/AppShell'
import { LoginDrawer } from '@/features/auth/LoginDrawer'
import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { authSession } from '@/features/auth/authSession'
import { LandingPage } from '@/features/landing/LandingPage'
import { WorkbenchPage } from '@/features/workbench/WorkbenchPage'

function LoginRoute() {
  return (
    <>
      <LandingPage />
      <LoginDrawer />
    </>
  )
}

function PlaceholderPage({ title }: { title: string }) {
  return (
    <main>
      <h1>{title}</h1>
      <p>该能力将在后续 M4 切片接入。</p>
    </main>
  )
}

function AuthenticatedShell() {
  const auth = useSyncExternalStore(authSession.subscribe, authSession.getSnapshot)
  if (!auth.user) return null
  return (
    <AppShell user={auth.user}>
      <Outlet />
    </AppShell>
  )
}

export const router = createBrowserRouter([
  { path: '/', element: <LandingPage /> },
  { path: '/login', element: <LoginRoute /> },
  {
    element: (
      <ProtectedRoute>
        <AuthenticatedShell />
      </ProtectedRoute>
    ),
    children: [
      { path: '/workbench', element: <WorkbenchPage /> },
      { path: '/chat', element: <PlaceholderPage title="据见问答" /> },
      { path: '/chat/history', element: <PlaceholderPage title="问答历史" /> },
      { path: '/knowledge-bases', element: <PlaceholderPage title="知识库" /> },
      { path: '/research/new', element: <PlaceholderPage title="深度研究" /> },
      { path: '/research', element: <PlaceholderPage title="研究任务" /> },
    ],
  },
  { path: '*', element: <LandingPage /> },
])
