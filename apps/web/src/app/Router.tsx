import { createBrowserRouter } from 'react-router-dom'

import { LoginDrawer } from '@/features/auth/LoginDrawer'
import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { LandingPage } from '@/features/landing/LandingPage'
import { WorkbenchPage } from '@/features/workbench/WorkbenchPage'

function LoginRoute() {
  return <><LandingPage /><LoginDrawer /></>
}

export const router = createBrowserRouter([
  { path: '/', element: <LandingPage /> },
  { path: '/login', element: <LoginRoute /> },
  {
    path: '/workbench',
    element: <ProtectedRoute><WorkbenchPage /></ProtectedRoute>,
  },
  { path: '*', element: <LandingPage /> },
])
