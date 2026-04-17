import { FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { AxiosError } from 'axios'

import { login, type LoginResponse } from '../api/auth'
import { useAuthStore } from '../store/auth'

interface ApiError {
  detail?: string
}

export function LoginPage() {
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const mutation = useMutation<LoginResponse, AxiosError<ApiError>, { email: string; password: string }>({
    mutationFn: login,
    onSuccess: (data) => {
      setAuth({ token: data.access_token, user: data.user })
      navigate('/app', { replace: true })
    },
  })

  if (token) {
    return <Navigate to="/app" replace />
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!email || !password) return
    mutation.mutate({ email: email.trim(), password })
  }

  const errorText = (() => {
    if (!mutation.isError) return null
    const detail = mutation.error?.response?.data?.detail
    if (detail) return detail
    if (mutation.error?.response?.status === 401) return 'Неверные учётные данные'
    return 'Не удалось войти. Попробуйте ещё раз.'
  })()

  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <section className="w-full max-w-md bg-white shadow-sm rounded-xl p-8 space-y-6 border border-slate-200">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold text-slate-900">Вход врача</h1>
          <p className="text-sm text-slate-500">AI-ассистент врача на приёме</p>
        </header>

        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
          <label className="block">
            <span className="block text-sm font-medium text-slate-700 mb-1">Email</span>
            <input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-300"
              placeholder="demo@clinic.local"
              disabled={mutation.isPending}
            />
          </label>

          <label className="block">
            <span className="block text-sm font-medium text-slate-700 mb-1">Пароль</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-300"
              disabled={mutation.isPending}
            />
          </label>

          {errorText && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {errorText}
            </div>
          )}

          <button
            type="submit"
            disabled={mutation.isPending || !email || !password}
            className="w-full inline-flex items-center justify-center rounded-lg bg-slate-900 px-5 py-2.5 text-white font-medium hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed transition"
          >
            {mutation.isPending ? 'Входим…' : 'Войти'}
          </button>
        </form>
      </section>
    </main>
  )
}
