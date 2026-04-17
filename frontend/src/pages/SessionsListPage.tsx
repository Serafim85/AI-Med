import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { listSessions, type SessionListResponse } from '../api/sessions'
import {
  APPOINTMENT_TYPE_LABEL,
  SEX_LABEL,
  STATUS_BADGE,
  STATUS_LABEL,
  formatDate,
} from '../lib/formatters'

const PAGE_SIZE = 50

export function SessionsListPage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const offset = (page - 1) * PAGE_SIZE

  const { data, isLoading, isError } = useQuery<SessionListResponse>({
    queryKey: ['sessions', { offset, limit: PAGE_SIZE }],
    queryFn: () => listSessions({ limit: PAGE_SIZE, offset }),
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <section className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            Приёмы
          </h1>
          <p className="text-sm text-slate-500">
            Все ваши сессии
          </p>
        </div>
        <Link
          to="/app/sessions/new"
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-medium hover:bg-slate-700 transition"
        >
          + Новый приём
        </Link>
      </header>

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

      {data && data.items.length === 0 && (
        <div className="bg-white border border-dashed border-slate-300 rounded-xl p-10 text-center text-slate-500">
          Пока нет ни одной сессии. Нажмите «Новый приём», чтобы начать.
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
                <th className="text-left px-4 py-3 font-medium">Статус</th>
                <th className="text-left px-4 py-3 font-medium">Создан</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((s) => (
                <tr
                  key={s.id}
                  className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer"
                  onClick={() => navigate(`/app/sessions/${s.id}`)}
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
