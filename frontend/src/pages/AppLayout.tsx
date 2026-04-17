import { Outlet, useNavigate } from 'react-router-dom'

import { useAuthStore } from '../store/auth'

export function AppLayout() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clear = useAuthStore((s) => s.clear)

  const handleLogout = () => {
    clear()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-3">
          <button
            type="button"
            onClick={() => navigate('/app')}
            className="flex items-center gap-3"
          >
            <span className="text-slate-900 font-semibold">
              AI-ассистент врача
            </span>
            {user && (
              <span className="text-slate-500 text-sm">
                · {user.full_name}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="text-sm rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-100 transition"
          >
            Выйти
          </button>
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="max-w-6xl mx-auto w-full">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
