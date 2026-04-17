import { useEffect, useRef, useState } from 'react'

import type { Protocol, ProtocolPatchPayload } from '../../api/analysis'

interface Props {
  protocol: Protocol
  disabled: boolean
  onPatch: (payload: ProtocolPatchPayload) => Promise<void> | void
}

interface FieldDef {
  key: keyof Omit<Protocol, 'id' | 'session_id' | 'confirmed_at' | 'created_at' | 'updated_at' | 'final_diagnosis' | 'icd10_code'>
  label: string
  rows: number
}

const FIELDS: FieldDef[] = [
  { key: 'complaints', label: 'Жалобы', rows: 3 },
  { key: 'anamnesis', label: 'Анамнез', rows: 3 },
  { key: 'examination', label: 'Осмотр', rows: 3 },
  { key: 'allergies', label: 'Аллергии', rows: 2 },
  { key: 'medications', label: 'Принимаемые препараты', rows: 2 },
]

/** Debounced autosave textarea bound to a single protocol field. */
function DebouncedField({
  label,
  rows,
  value,
  disabled,
  onCommit,
}: {
  label: string
  rows: number
  value: string
  disabled: boolean
  onCommit: (next: string) => Promise<void> | void
}) {
  const [local, setLocal] = useState(value)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const timer = useRef<number | null>(null)
  const lastSaved = useRef<string>(value)

  useEffect(() => {
    // External updates (e.g. after analysis re-run) reset the field.
    if (value !== lastSaved.current) {
      setLocal(value)
      lastSaved.current = value
    }
  }, [value])

  useEffect(() => {
    if (local === lastSaved.current) return
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      setSaving(true)
      try {
        await onCommit(local)
        lastSaved.current = local
        setSavedAt(Date.now())
      } finally {
        setSaving(false)
      }
    }, 800)
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [local, onCommit])

  return (
    <label className="block">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <span className="text-xs text-slate-400">
          {saving
            ? 'Сохранение…'
            : savedAt
              ? 'Сохранено'
              : ''}
        </span>
      </div>
      <textarea
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:bg-slate-50 disabled:cursor-not-allowed"
        rows={rows}
        value={local}
        disabled={disabled}
        onChange={(e) => setLocal(e.target.value)}
      />
    </label>
  )
}

export function ProtocolPanel({ protocol, disabled, onPatch }: Props) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
      <h3 className="text-lg font-semibold text-slate-900">
        Структурированный протокол
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {FIELDS.map((f) => (
          <DebouncedField
            key={f.key}
            label={f.label}
            rows={f.rows}
            value={protocol[f.key] ?? ''}
            disabled={disabled}
            onCommit={async (next) => {
              await onPatch({ [f.key]: next } as ProtocolPatchPayload)
            }}
          />
        ))}
      </div>
      {(protocol.final_diagnosis || protocol.icd10_code) && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm">
          <div className="font-medium text-emerald-900">
            Итоговый диагноз: {protocol.final_diagnosis ?? '—'}
          </div>
          {protocol.icd10_code && (
            <div className="text-xs text-emerald-800">
              МКБ-10: {protocol.icd10_code}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
