import { Link, useParams } from 'react-router-dom'

/** Step-5 placeholder: the actual confirmation + PDF export is implemented
 * in the next step. We keep a real route here so the "К итоговому
 * протоколу" button in the analysis panel navigates somewhere sensible.
 */
export function SessionConfirmPage() {
  const { id = '' } = useParams<{ id: string }>()
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-8 space-y-4 max-w-2xl">
      <h1 className="text-xl font-semibold text-slate-900">
        Подтверждение и PDF
      </h1>
      <p className="text-sm text-slate-600">
        Экран итогового подтверждения протокола и формирование PDF появятся
        в Шаге 5. Сейчас данные анализа сохранены на стороне сервера
        (статус сессии — «Обработан»).
      </p>
      <Link
        to={`/app/sessions/${id}`}
        className="inline-flex items-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
      >
        ← Назад к сессии
      </Link>
    </section>
  )
}
