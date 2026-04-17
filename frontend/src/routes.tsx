import { Navigate, Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from './components/ProtectedRoute'
import { AppLayout } from './pages/AppLayout'
import { LoginPage } from './pages/LoginPage'
import { SessionCreatePage } from './pages/SessionCreatePage'
import { SessionDetailPage } from './pages/SessionDetailPage'
import { SessionsListPage } from './pages/SessionsListPage'
import { useAuthStore } from './store/auth'

function RootRedirect() {
  const token = useAuthStore((s) => s.token)
  return <Navigate to={token ? '/app' : '/login'} replace />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<SessionsListPage />} />
        <Route path="sessions/new" element={<SessionCreatePage />} />
        <Route path="sessions/:id" element={<SessionDetailPage />} />
      </Route>
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  )
}
