import { useState } from 'react'

import type { RedFlag } from '../../api/analysis'
import { SEVERITY_BADGE, SEVERITY_LABEL } from '../../lib/formatters'

interface Props {
  redFlags: RedFlag[]
  disabled: boolean
  onAcknowledge: (
    redFlagId: string,
    payload: { accepted: boolean; note?: string | null },
  ) => Promise<void> | void
}

export function RedFlagsPanel({ redFlags, disabled, onAcknowledge }: Props) {
  if (redFlags.length === 0) return null
  return (
    <section className="rounded-xl border border-red-200 overflow-hidden bg-white">
      <div className="bg-red-600 text-white px-5 py-2 text-sm font-semibold uppercase tracking-wide">
        Красные флаги
      </div>
      <div className="p-5 space-y-3">
        {redFlags.map((flag) => (
          <RedFlagCard
            key={flag.id}
            flag={flag}
            disabled={disabled}
            onAcknowledge={(payload) => onAcknowledge(flag.id, payload)}
          />
        ))}
      </div>
    </section>
  )
}

function RedFlagCard({
  flag,
  disabled,
  onAcknowledge,
}: {
  flag: RedFlag
  disabled: boolean
  onAcknowledge: (payload: {
    accepted: boolean
    note?: string | null
  }) => Promise<void> | void
}) {
  const [rejectOpen, setRejectOpen] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const severityClass = flag.severity
    ? SEVERITY_BADGE[flag.severity]
    : 'bg-slate-100 text-slate-600 border-slate-200'
  const acknowledged = flag.acknowledged_at !== null

  const handleAccept = async () => {
    setBusy(true)
    try {
      await onAcknowledge({ accepted: true, note: null })
    } finally {
      setBusy(false)
    }
  }

  const handleReject = async () => {
    if (!note.trim()) return
    setBusy(true)
    try {
      await onAcknowledge({ accepted: false, note: note.trim() })
      setRejectOpen(false)
      setNote('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg border border-red-200 bg-red-50/50 p-4">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h4 className="font-semibold text-slate-900">{flag.label}</h4>
          {flag.description && (
            <p className="text-sm text-slate-700 mt-1">{flag.description}</p>
          )}
        </div>
        {flag.severity && (
          <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${severityClass}`}
          >
            {SEVERITY_LABEL[flag.severity]}
          </span>
        )}
      </div>

      {acknowledged ? (
        <div className="text-xs text-slate-600 bg-white rounded border border-slate-200 px-3 py-2">
          {flag.doctor_note
            ? `Отклонено: ${flag.doctor_note}`
            : 'Подтверждено врачом'}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleAccept}
            disabled={busy || disabled}
            className="rounded-md bg-red-600 text-white px-3 py-1.5 text-sm font-medium hover:bg-red-500 disabled:opacity-60"
          >
            Принять
          </button>
          {!rejectOpen && (
            <button
              type="button"
              onClick={() => setRejectOpen(true)}
              disabled={busy || disabled}
              className="rounded-md border border-slate-300 text-slate-700 px-3 py-1.5 text-sm font-medium hover:bg-slate-100 disabled:opacity-60"
            >
              Отклонить
            </button>
          )}
          {rejectOpen && (
            <div className="flex-1 min-w-[240px] flex flex-col gap-2">
              <textarea
                className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
                placeholder="Причина отклонения (обязательно)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleReject}
                  disabled={busy || disabled || !note.trim()}
                  className="rounded-md bg-slate-900 text-white px-3 py-1.5 text-sm font-medium hover:bg-slate-700 disabled:opacity-60"
                >
                  Отклонить
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setRejectOpen(false)
                    setNote('')
                  }}
                  disabled={busy}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-100"
                >
                  Отмена
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
