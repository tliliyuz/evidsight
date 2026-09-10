import { useEffect, type PropsWithChildren } from 'react'

import { authSession } from '@/features/auth/authSession'

export function AuthBootstrap({ children }: PropsWithChildren) {
  useEffect(() => {
    void authSession.restore()
  }, [])

  return children
}
