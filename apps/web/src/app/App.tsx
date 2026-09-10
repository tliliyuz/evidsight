import { RouterProvider } from 'react-router-dom'

import { AppErrorBoundary } from '@/app/ErrorBoundary'
import { AppProviders } from '@/app/Providers'
import { router } from '@/app/Router'
import { AuthBootstrap } from '@/features/auth/AuthBootstrap'
import { initializeTheme } from '@/state/theme'

initializeTheme()

export function App() {
  return (
    <AppErrorBoundary>
      <AppProviders>
        <AuthBootstrap>
          <RouterProvider router={router} />
        </AuthBootstrap>
      </AppProviders>
    </AppErrorBoundary>
  )
}
