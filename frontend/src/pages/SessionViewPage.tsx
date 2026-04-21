import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  closeSession,
  downloadSessionPdf,
  getSessionSummary,
  type SessionSummary,
} from '../api/finalization'
import { SessionSummaryView } from '../components/SessionSummaryView'

interface ApiError {
  detail?: string
}

function extractDetail(err: unknown, fallback: string): string {
  const ax = err as AxiosError<ApiError>
  return ax?.response?.data?.detail ?? fallback
}

/** Read-only view for confirmed / closed sessions.
 *
 * If the session is still ``draft``/``recording``/``analyzed`` we redirect
 * back to ``/app/sessions/:id`` so the doctor can keep editing.
 */
export function SessionViewPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  // Guards against double downloads from fast double-clicks / StrictMode.
  const downloadingRef = useRef(false)

  const summaryQuery = useQuery<SessionSummary>({
    queryKey: ['session-summary', id],
    queryFn: () => getSessionSummary(id),
    enabled: !!id,
    retry: false,
  })

  useEffect(() => {
    const status = summaryQuery.data?.session.status
    if (status && status !== 'confirmed' && status !== 'closed') {
      navigate(`/app/sessions/${id}`, { replace: true })
    }
  }, [id, navigate, summaryQuery.data?.session.status])

  const closeMutation = useMutation({
    mutationFn: () => closeSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session-summary', id] })
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      setToast('Приём завершён.')
    },
    onError: (err) => setError(extractDetail(err, 'Не удалось завершить приём')),
  })

  const handleDownload = async () => {
    if (downloadingRef.current) return
    downloadingRef.current = true
    try {
      await downloadSessionPdf(id)
    } catch (err) {
      setError(extractDetail(err, 'Не удалось скачать PDF'))
    } finally {
      downloadingRef.current = false
    }
  }

  if (summaryQuery.isLoading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-slate-500">
        Загрузка…
      </div>
    )
  }

  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 p-6 space-y-3">
        <p>
          {extractDetail(
            summaryQuery.error,
            'Не удалось загрузить сессию',
          )}
        </p>
        <Link to="/app" className="text-sm underline">
          Назад к списку
        </Link>
      </div>
    )
  }

  const summary = summaryQuery.data
  const status = summary.session.status
  const canClose = status === 'confirmed'

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-900">
          Просмотр сессии
        </h1>
        <Link
          to="/app"
          className="text-sm text-slate-500 hover:underline"
        >
          ← К списку
        </Link>
      </div>

      {toast && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm">
          {toast}
        </div>
      )}

      <SessionSummaryView summary={summary} allowEdit={false} />

      <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 text-red-700 px-4 py-2 text-sm">
            {error}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleDownload}
            className="inline-flex items-center rounded-lg bg-sky-600 text-white px-4 py-2 text-sm font-medium hover:bg-sky-500"
          >
            Скачать PDF
          </button>
          {canClose && (
            <button
              type="button"
              onClick={() => closeMutation.mutate()}
              disabled={closeMutation.isPending}
              className="inline-flex items-center rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-medium hover:bg-slate-700 disabled:opacity-60"
            >
              {closeMutation.isPending ? 'Закрываем…' : 'Завершить приём'}
            </button>
          )}
        </div>
      </section>
    </section>
  )
}
