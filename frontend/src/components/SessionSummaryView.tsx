import { useMemo } from 'react'
import { Link } from 'react-router-dom'

import type { SessionSummary } from '../api/finalization'
import {
  APPOINTMENT_TYPE_LABEL,
  SEVERITY_BADGE,
  SEVERITY_LABEL,
  SEX_LABEL,
  STATUS_BADGE,
  STATUS_LABEL,
  TREATMENT_KIND_LABEL,
  TREATMENT_KIND_ORDER,
  formatDate,
} from '../lib/formatters'

interface Props {
  summary: SessionSummary
  /** Show "Edit" back-links next to each block (true on /confirm, false on /view). */
  allowEdit: boolean
}

/** Read-only rendering of the aggregated session summary used on both
 * ``/confirm`` and ``/view`` screens. */
export function SessionSummaryView({ summary, allowEdit }: Props) {
  const { session, doctor, protocol, selected_diagnosis, red_flags, treatment_plan_items } =
    summary

  const unresolvedFlags = red_flags.filter((f) => !f.acknowledged_at)

  const groupedPlan = useMemo(() => {
    const groups = new Map<string, typeof treatment_plan_items>()
    for (const item of treatment_plan_items) {
      const arr = groups.get(item.kind) ?? []
      arr.push(item)
      groups.set(item.kind, arr)
    }
    return TREATMENT_KIND_ORDER.filter((kind) => groups.has(kind)).map((kind) => ({
      kind,
      items: (groups.get(kind) ?? []).slice().sort(
        (a, b) => a.order_index - b.order_index,
      ),
    }))
  }, [treatment_plan_items])

  const editHref = `/app/sessions/${session.id}`

  const ReadOnlyBlock = ({
    title,
    body,
  }: {
    title: string
    body: string
  }) => (
    <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
          {title}
        </h3>
        {allowEdit && (
          <Link
            to={editHref}
            className="text-xs text-sky-700 hover:underline"
          >
            Редактировать
          </Link>
        )}
      </div>
      <p className="text-sm text-slate-800 whitespace-pre-wrap">
        {body && body.trim() ? body : <span className="text-slate-400 italic">—</span>}
      </p>
    </section>
  )

  return (
    <div className="space-y-4">
      {/* 1. Header */}
      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">
              Приём от {formatDate(session.created_at)}
            </div>
            <h1 className="text-2xl font-semibold text-slate-900">
              {session.patient_full_name}
            </h1>
            <p className="text-sm text-slate-600 mt-1">
              {session.patient_age} лет · {SEX_LABEL[session.patient_sex]} ·{' '}
              {APPOINTMENT_TYPE_LABEL[session.appointment_type]}
            </p>
            <p className="text-sm text-slate-600">Врач: {doctor.full_name}</p>
          </div>
          <span
            className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${STATUS_BADGE[session.status]}`}
          >
            {STATUS_LABEL[session.status]}
          </span>
        </div>
      </section>

      {/* 2. Protocol blocks */}
      {protocol ? (
        <>
          <ReadOnlyBlock title="Жалобы" body={protocol.complaints} />
          <ReadOnlyBlock title="Анамнез" body={protocol.anamnesis} />
          <ReadOnlyBlock title="Осмотр" body={protocol.examination} />
          <div className="grid md:grid-cols-2 gap-4">
            <ReadOnlyBlock title="Аллергии" body={protocol.allergies} />
            <ReadOnlyBlock
              title="Принимаемые препараты"
              body={protocol.medications}
            />
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-amber-200 bg-amber-50 text-amber-800 p-4 text-sm">
          Протокол не сформирован — сначала выполните анализ.
        </div>
      )}

      {/* 3. Final diagnosis */}
      <section
        className={`rounded-xl border p-5 ${
          selected_diagnosis
            ? 'border-emerald-200 bg-emerald-50'
            : 'border-red-200 bg-red-50'
        }`}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
            Итоговый диагноз
          </h3>
          {allowEdit && (
            <Link
              to={editHref}
              className="text-xs text-sky-700 hover:underline"
            >
              Редактировать
            </Link>
          )}
        </div>
        {selected_diagnosis ? (
          <div className="mt-2">
            <p className="text-lg font-semibold text-slate-900">
              {selected_diagnosis.title}
            </p>
            {selected_diagnosis.icd10_code && (
              <p className="text-sm text-slate-600 mt-1">
                МКБ-10: <span className="font-mono">{selected_diagnosis.icd10_code}</span>
              </p>
            )}
          </div>
        ) : (
          <p className="mt-2 text-red-700 text-sm font-medium">
            Диагноз не выбран
          </p>
        )}
      </section>

      {/* 4. Red flags */}
      {red_flags.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 bg-slate-50 border-b border-slate-200">
            <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
              Красные флаги
            </h3>
            {allowEdit && (
              <Link
                to={editHref}
                className="text-xs text-sky-700 hover:underline"
              >
                Редактировать
              </Link>
            )}
          </div>
          {unresolvedFlags.length > 0 && (
            <div className="bg-red-50 text-red-800 text-sm px-5 py-2 border-b border-red-200">
              Есть {unresolvedFlags.length} необработанн
              {unresolvedFlags.length === 1 ? 'ый' : 'ых'} флаг
              {unresolvedFlags.length === 1 ? '' : 'ов'} — вернитесь в анализ и
              отметьте их.
            </div>
          )}
          <ul className="divide-y divide-slate-100">
            {red_flags.map((rf) => {
              const accepted =
                rf.acknowledged_at !== null && !rf.doctor_note
              const dismissed =
                rf.acknowledged_at !== null && !!rf.doctor_note
              return (
                <li key={rf.id} className="px-5 py-3 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-slate-900">
                      {rf.label}
                    </span>
                    {rf.severity && (
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY_BADGE[rf.severity]}`}
                      >
                        {SEVERITY_LABEL[rf.severity]}
                      </span>
                    )}
                    {accepted && (
                      <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium bg-emerald-50 text-emerald-700 border-emerald-200">
                        Принято
                      </span>
                    )}
                    {dismissed && (
                      <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-600 border-slate-200">
                        Отклонено
                      </span>
                    )}
                    {!rf.acknowledged_at && (
                      <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 border-red-300">
                        Не обработан
                      </span>
                    )}
                  </div>
                  {rf.description && (
                    <p className="text-sm text-slate-600">{rf.description}</p>
                  )}
                  {rf.doctor_note && (
                    <p className="text-sm text-slate-700">
                      <em className="text-slate-500">Комментарий врача:</em>{' '}
                      {rf.doctor_note}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {/* 5. Treatment plan */}
      <section className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 bg-slate-50 border-b border-slate-200">
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
            План лечения
          </h3>
          {allowEdit && (
            <Link
              to={editHref}
              className="text-xs text-sky-700 hover:underline"
            >
              Редактировать
            </Link>
          )}
        </div>
        {groupedPlan.length === 0 ? (
          <div className="px-5 py-4 text-sm text-slate-500 italic">
            План лечения пуст.
          </div>
        ) : (
          <div className="p-5 space-y-4">
            {groupedPlan.map((group) => (
              <div key={group.kind}>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
                  {TREATMENT_KIND_LABEL[group.kind]}
                </h4>
                <ul className="space-y-2">
                  {group.items.map((item) => (
                    <li
                      key={item.id}
                      className="rounded-lg border border-slate-200 bg-white p-3"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-medium text-slate-900">
                          {item.title}
                        </div>
                        <span
                          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${
                            item.is_confirmed
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-slate-100 text-slate-500 border-slate-200'
                          }`}
                        >
                          {item.is_confirmed ? 'Подтверждён' : 'Не подтверждён'}
                        </span>
                      </div>
                      {(item.dosage || item.duration) && (
                        <div className="text-xs text-slate-500 mt-1 flex gap-3">
                          {item.dosage && <span>Доза: {item.dosage}</span>}
                          {item.duration && (
                            <span>Длительность: {item.duration}</span>
                          )}
                        </div>
                      )}
                      {item.details && (
                        <p className="text-sm text-slate-600 mt-1">
                          {item.details}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
