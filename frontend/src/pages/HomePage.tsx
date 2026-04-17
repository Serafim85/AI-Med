import { useMutation } from '@tanstack/react-query'

import { fetchHealth, type HealthResponse } from '../api/health'

export function HomePage() {
  const mutation = useMutation<HealthResponse, Error>({
    mutationFn: fetchHealth,
  })

  const renderResult = () => {
    if (mutation.isPending) {
      return <p className="text-slate-500">Проверяем…</p>
    }
    if (mutation.isError) {
      return (
        <p className="text-red-600">
          Ошибка: {mutation.error.message}
        </p>
      )
    }
    if (mutation.data) {
      return (
        <pre className="rounded bg-slate-900 text-slate-100 p-3 text-sm overflow-x-auto">
          {JSON.stringify(mutation.data, null, 2)}
        </pre>
      )
    }
    return <p className="text-slate-500">Нажмите кнопку, чтобы проверить backend.</p>
  }

  return (
    <main className="min-h-full flex items-center justify-center bg-slate-50 p-6">
      <section className="w-full max-w-xl bg-white shadow-sm rounded-xl p-8 space-y-6 border border-slate-200">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">
            AI-ассистент врача
          </h1>
          <p className="text-slate-600">
            Скелет приложения. Проверьте, что backend отвечает на health-check.
          </p>
        </header>

        <button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-5 py-2.5 text-white font-medium hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed transition"
        >
          Проверить health-check
        </button>

        <div>{renderResult()}</div>
      </section>
    </main>
  )
}
