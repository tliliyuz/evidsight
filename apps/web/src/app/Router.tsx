import { useSyncExternalStore } from 'react'
import { createBrowserRouter, Outlet, type RouteObject } from 'react-router-dom'

import { ToastProvider } from '@/components/feedback/ToastProvider'
import { AppShell } from '@/app/AppShell'
import { LoginDrawer } from '@/features/auth/LoginDrawer'
import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { authSession } from '@/features/auth/authSession'
import { ChatPage } from '@/features/chat/ChatPage'
import { ConversationHistoryPage } from '@/features/chat/ConversationHistoryPage'
import { KnowledgeBaseDetailPage } from '@/features/knowledge/KnowledgeBaseDetailPage'
import { KnowledgeBaseListPage } from '@/features/knowledge/KnowledgeBaseListPage'
import { LandingPage } from '@/features/landing/LandingPage'
import { WorkbenchPage } from '@/features/workbench/WorkbenchPage'

/** 入口页常驻布局：抽屉作为浮层叠加，关闭后入口页滚动位置与焦点保留。 */
function LandingLayout() {
  return (
    <>
      <LandingPage />
      <Outlet />
    </>
  )
}

/**
 * 路由根 layout：ToastProvider 必须挂在全部路由之上（FRONTEND §5.1/§10），
 * 登录（LandingLayout）与登录后工作区共用同一个 Provider 实例——
 * 若只包登录后壳层，/login 路由树内 `useAppToast()` 会落到 no-op，
 * 登录成功反馈永不显示（曾真实发生，见复核修正十）。
 */
export function RootLayout() {
  return (
    <ToastProvider>
      <Outlet />
    </ToastProvider>
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

export const routes: RouteObject[] = [
  {
    element: <RootLayout />,
    children: [
      {
        element: <LandingLayout />,
        children: [
          { index: true, element: null },
          { path: '/login', element: <LoginDrawer /> },
        ],
      },
      {
        element: (
          <ProtectedRoute>
            <AuthenticatedShell />
          </ProtectedRoute>
        ),
        children: [
          { path: '/workbench', element: <WorkbenchPage /> },
          { path: '/chat', element: <ChatPage /> },
          { path: '/chat/history', element: <ConversationHistoryPage /> },
          { path: '/knowledge-bases', element: <KnowledgeBaseListPage /> },
          { path: '/knowledge-bases/:kbId', element: <KnowledgeBaseDetailPage /> },
          { path: '/research/new', element: <PlaceholderPage title="深度研究" /> },
          { path: '/research', element: <PlaceholderPage title="研究任务" /> },
          { path: '/research/:taskId', element: <PlaceholderPage title="研究任务" /> },
        ],
      },
      { path: '*', element: <LandingPage /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
