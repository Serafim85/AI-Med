import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  closeSession,
  confirmSession,
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

export function SessionConfirmPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [pdfReady, setPdfReady] = useState(false)

  const summaryQuery = useQuery<SessionSummary>({
    queryKey: ['session-summary', id],
    queryFn: () => getSessionSummary(id),
    enabled: !!id,
    retry: false,
  })

  // If summary is 409 (wrong status) — send the user back to analysis.
  useEffect(() => {
    const err = summaryQuery.error as AxiosError<ApiError> | null
    if (err?.response?.status === 409) {
      window.alert('Сначала выполните анализ приёма.')
      navigate(`/app/sessions/${id}`, { replace: true })
    }
  }, [id, navigate, summaryQuery.error])

  const status = summaryQuery.data?.session.status
  const isAnalyzed = status === 'analyzed'
  const isConfirmed = status === 'confirmed'
  const isClosed = status === 'closed'

  // ---------------------------------------------------------------------
  // Navigation guard: warn when leaving /confirm without confirming.
  // ---------------------------------------------------------------------

  useEffect(() => {
    if (!isAnalyzed) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isAnalyzed])

  const guardedNavigate = useCallback(
    (to: string, replace = false) => {
      if (
        isAnalyzed &&
        !window.confirm(
          'Протокол не подтверждён. Сохранить как черновик и выйти?',
        )
      ) {
        return
      }
      navigate(to, { replace })
    },
    [isAnalyzed, navigate],
  )

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['session-summary', id] })
    queryClient.invalidateQueries({ queryKey: ['session', id] })
    queryClient.invalidateQueries({ queryKey: ['analysis', id] })
    queryClient.invalidateQueries({ queryKey: ['sessions'] })
  }

  const confirmMutation = useMutation({
    mutationFn: () => confirmSession(id),
    onSuccess: async () => {
      setConfirmError(null)
      invalidate()
      try {
        await downloadSessionPdf(id)
        setPdfReady(true)
        setToast('Протокол подтверждён. PDF сохранён.')
      } catch (err) {
        setToast(null)
        setConfirmError(extractDetail(err, 'PDF не удалось скачать'))
      }
    },
    onError: (err) => {
      setConfirmError(extractDetail(err, 'Не удалось подтвердить протокол'))
    },
  })

  const closeMutation = useMutation({
    mutationFn: () => closeSession(id),
    onSuccess: () => {
      invalidate()
      setToast('Приём завершён. Сессия закрыта.')
      setTimeout(() => navigate('/app'), 800)
    },
    onError: (err) => {
      setConfirmError(extractDetail(err, 'Не удалось завершить приём'))
    },
  })

  const handleDownloadPdf = async () => {
    try {
      await downloadSessionPdf(id)
    } catch (err) {
      setConfirmError(extractDetail(err, 'PDF не удалось скачать'))
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
            'Не удалось загрузить итоговую карточку',
          )}
        </p>
        <Link to={`/app/sessions/${id}`} className="text-sm underline">
          Вернуться к анализу
        </Link>
      </div>
    )
  }

  const summary = summaryQuery.data

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-900">
          Итоговый протокол
        </h1>
        <button
          type="button"
          onClick={() => guardedNavigate('/app')}
          className="text-sm text-slate-500 hover:underline"
        >
          ← К списку
        </button>
      </div>

      {toast && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm">
          {toast}
        </div>
      )}

      <SessionSummaryView summary={summary} allowEdit={isAnalyzed} />

      {/* Bottom action panel */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
        {confirmError && (
          <div className="rounded-lg border border-red-200 bg-red-50 text-red-700 px-4 py-2 text-sm">
            {confirmError}
          </div>
        )}

        {isAnalyzed && (
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => {
                setConfirmError(null)
                confirmMutation.mutate()
              }}
              disabled={confirmMutation.isPending}
              className="inline-flex items-center rounded-lg bg-emerald-600 text-white px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-60"
            >
              {confirmMutation.isPending
                ? 'Подтверждаем…'
                : 'Подтвердить и сформировать PDF'}
            </button>
            <button
              type="button"
              onClick={() => guardedNavigate(`/app/sessions/${id}`)}
              className="inline-flex items-center rounded-lg border border-slate-300 text-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-100"
            >
              Вернуться к анализу
            </button>
          </div>
        )}

        {isConfirmed && (
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleDownloadPdf}
              className="inline-flex items-center rounded-lg bg-sky-600 text-white px-4 py-2 text-sm font-medium hover:bg-sky-500"
            >
              {pdfReady ? 'Скачать PDF ещё раз' : 'Скачать PDF'}
            </button>
            <button
              type="button"
              onClick={() => closeMutation.mutate()}
              disabled={closeMutation.isPending}
              className="inline-flex items-center rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-medium hover:bg-slate-700 disabled:opacity-60"
            >
              {closeMutation.isPending ? 'Закрываем…' : 'Завершить приём'}
            </button>
          </div>
        )}

        {isClosed && (
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleDownloadPdf}
              className="inline-flex items-center rounded-lg bg-sky-600 text-white px-4 py-2 text-sm font-medium hover:bg-sky-500"
            >
              Скачать PDF
            </button>
            <Link
              to="/app"
              className="inline-flex items-center rounded-lg border border-slate-300 text-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-100"
            >
              К списку
            </Link>
          </div>
        )}
      </section>
    </section>
  )
}
