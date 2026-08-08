import { type PropsWithChildren, useSyncExternalStore } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { authSession } from '@/features/auth/authSession'

export function ProtectedRoute({ children }: PropsWithChildren) {
  const auth = useSyncExternalStore(authSession.subscribe, authSession.getSnapshot)
  const location = useLocation()

  if (auth.status === 'restoring') {
    return <main aria-live="polite">正在恢复身份…</main>
  }
  if (auth.status === 'anonymous') {
    return <Navigate to="/login" replace state={{ returnTo: location.pathname }} />
  }
  return children
}
