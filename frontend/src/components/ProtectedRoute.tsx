import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'

import { useAuthStore } from '../store/auth'

interface ProtectedRouteProps {
  children: ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const token = useAuthStore((s) => s.token)
  const bootstrapped = useAuthStore((s) => s.bootstrapped)
  const location = useLocation()

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (!bootstrapped) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Загрузка…
      </div>
    )
  }

  return <>{children}</>
}
