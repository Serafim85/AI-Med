import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import {
  listSessions,
  type SessionListResponse,
  type SessionStatus,
} from '../api/sessions'
import {
  APPOINTMENT_TYPE_LABEL,
  SEX_LABEL,
  STATUS_BADGE,
  STATUS_LABEL,
  formatDate,
} from '../lib/formatters'

const PAGE_SIZE = 50

type TabKey = 'all' | SessionStatus

const TABS: { key: TabKey; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'draft', label: 'Черновики' },
  { key: 'recording', label: 'В процессе' },
  { key: 'analyzed', label: 'Проанализированы' },
  { key: 'confirmed', label: 'Подтверждённые' },
  { key: 'closed', label: 'Закрытые' },
]

function routeForSession(status: SessionStatus, id: string): string {
  if (status === 'confirmed' || status === 'closed') {
    return `/app/sessions/${id}/view`
  }
  if (status === 'analyzed') {
    return `/app/sessions/${id}/confirm`
  }
  return `/app/sessions/${id}`
}

export function SessionsListPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<TabKey>('all')
  const [queryInput, setQueryInput] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)

  // debounce query
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(queryInput.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [queryInput])

  useEffect(() => {
    setPage(1)
  }, [tab])

  const offset = (page - 1) * PAGE_SIZE

  const { data, isLoading, isError } = useQuery<SessionListResponse>({
    queryKey: ['sessions', { tab, query, offset, limit: PAGE_SIZE }],
    queryFn: () =>
      listSessions({
        limit: PAGE_SIZE,
        offset,
        status: tab,
        query: query || undefined,
      }),
  })

  const totalPages = useMemo(
    () => (data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1),
    [data],
  )

  return (
    <section className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Приёмы</h1>
          <p className="text-sm text-slate-500">Все ваши сессии</p>
        </div>
        <Link
          to="/app/sessions/new"
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-medium hover:bg-slate-700 transition"
        >
          + Новый приём
        </Link>
      </header>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`rounded-full border px-3 py-1 text-sm transition ${
                tab === t.key
                  ? 'bg-slate-900 text-white border-slate-900'
                  : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="search"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            placeholder="Поиск по ФИО пациента…"
            className="w-full max-w-md rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          {data && (
            <span className="text-xs text-slate-500">
              Найдено: {data.total}
            </span>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-slate-500">
          Загрузка…
        </div>
      )}

      {isError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-6">
          Не удалось загрузить список приёмов.
        </div>
      )}

      {data && data.items.length === 0 && !isLoading && (
        <div className="bg-white border border-dashed border-slate-300 rounded-xl p-10 text-center text-slate-500">
          {query || tab !== 'all'
            ? 'Ничего не найдено по выбранным фильтрам.'
            : 'Пока нет ни одной сессии. Нажмите «Новый приём», чтобы начать.'}
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Пациент</th>
                <th className="text-left px-4 py-3 font-medium">Возраст/пол</th>
                <th className="text-left px-4 py-3 font-medium">Тип</th>
                <th className="text-left px-4 py-3 font-medium">Диагноз</th>
                <th className="text-left px-4 py-3 font-medium">Статус</th>
                <th className="text-left px-4 py-3 font-medium">Создан</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((s) => (
                <tr
                  key={s.id}
                  className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer"
                  onClick={() => navigate(routeForSession(s.status, s.id))}
                >
                  <td className="px-4 py-3 font-medium text-slate-900">
                    {s.patient_full_name}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {s.patient_age} · {SEX_LABEL[s.patient_sex]}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {APPOINTMENT_TYPE_LABEL[s.appointment_type]}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {s.final_diagnosis ?? '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[s.status]}`}
                    >
                      {STATUS_LABEL[s.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {formatDate(s.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <button
            type="button"
            className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Назад
          </button>
          <span className="text-slate-600">
            Стр. {page} / {totalPages}
          </span>
          <button
            type="button"
            className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Вперёд
          </button>
        </div>
      )}
    </section>
  )
}
