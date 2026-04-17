import { useState } from 'react'

import type {
  CustomDiagnosisPayload,
  DiagnosisSuggestion,
} from '../../api/analysis'
import { formatProbability } from '../../lib/formatters'

interface Props {
  suggestions: DiagnosisSuggestion[]
  disabled: boolean
  onSelect: (suggestionId: string) => Promise<void> | void
  onCustom: (payload: CustomDiagnosisPayload) => Promise<void> | void
}

export function DiagnosesPanel({
  suggestions,
  disabled,
  onSelect,
  onCustom,
}: Props) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
      <h3 className="text-lg font-semibold text-slate-900">Топ-3 диагноза</h3>
      {suggestions.length === 0 ? (
        <p className="text-sm text-slate-500 italic">
          LLM не предложил диагнозы. Используйте форму «Указать свой диагноз».
        </p>
      ) : (
        <ul className="space-y-3">
          {suggestions.map((s) => (
            <SuggestionCard
              key={s.id}
              suggestion={s}
              disabled={disabled}
              onSelect={() => onSelect(s.id)}
            />
          ))}
        </ul>
      )}
      <CustomDiagnosisForm disabled={disabled} onSubmit={onCustom} />
    </section>
  )
}

function SuggestionCard({
  suggestion,
  disabled,
  onSelect,
}: {
  suggestion: DiagnosisSuggestion
  disabled: boolean
  onSelect: () => Promise<void> | void
}) {
  const [supportOpen, setSupportOpen] = useState(false)
  const [againstOpen, setAgainstOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const probability = suggestion.probability ?? 0

  const handleSelect = async () => {
    setBusy(true)
    try {
      await onSelect()
    } finally {
      setBusy(false)
    }
  }

  return (
    <li
      className={`rounded-lg border p-4 ${
        suggestion.is_selected
          ? 'border-emerald-400 bg-emerald-50 ring-1 ring-emerald-300'
          : 'border-slate-200 bg-white'
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h4 className="font-semibold text-slate-900">{suggestion.title}</h4>
          {suggestion.icd10_code && (
            <div className="text-xs text-slate-500">
              МКБ-10: {suggestion.icd10_code}
            </div>
          )}
        </div>
        <div className="text-sm font-medium text-slate-700">
          {formatProbability(suggestion.probability)}
        </div>
      </div>
      <div className="h-2 w-full rounded-full bg-slate-100 mb-3 overflow-hidden">
        <div
          className="h-full bg-sky-500"
          style={{ width: `${Math.round(probability * 100)}%` }}
        />
      </div>
      {suggestion.reasoning && (
        <p className="text-sm text-slate-700 mb-3">{suggestion.reasoning}</p>
      )}

      <div className="text-xs flex flex-wrap gap-4 mb-3">
        {suggestion.supporting_symptoms.length > 0 && (
          <button
            type="button"
            onClick={() => setSupportOpen((v) => !v)}
            className="text-sky-700 hover:underline"
          >
            {supportOpen ? '− За' : '+ За'} ({suggestion.supporting_symptoms.length})
          </button>
        )}
        {suggestion.contradicting_symptoms.length > 0 && (
          <button
            type="button"
            onClick={() => setAgainstOpen((v) => !v)}
            className="text-rose-700 hover:underline"
          >
            {againstOpen ? '− Против' : '+ Против'} (
            {suggestion.contradicting_symptoms.length})
          </button>
        )}
      </div>
      {supportOpen && (
        <ul className="text-sm text-slate-700 list-disc pl-5 mb-2">
          {suggestion.supporting_symptoms.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}
      {againstOpen && (
        <ul className="text-sm text-slate-700 list-disc pl-5 mb-2">
          {suggestion.contradicting_symptoms.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}

      <div>
        <button
          type="button"
          onClick={handleSelect}
          disabled={busy || disabled || suggestion.is_selected}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${
            suggestion.is_selected
              ? 'bg-emerald-600 text-white cursor-default'
              : 'bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-60'
          }`}
        >
          {suggestion.is_selected ? 'Выбрано' : 'Выбрать'}
        </button>
      </div>
    </li>
  )
}

function CustomDiagnosisForm({
  disabled,
  onSubmit,
}: {
  disabled: boolean
  onSubmit: (payload: CustomDiagnosisPayload) => Promise<void> | void
}) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [icd, setIcd] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const reset = () => {
    setTitle('')
    setIcd('')
    setReason('')
  }

  const submit = async () => {
    if (!title.trim()) return
    setBusy(true)
    try {
      await onSubmit({
        title: title.trim(),
        icd10_code: icd.trim() || null,
        reason: reason.trim() || null,
      })
      reset()
      setOpen(false)
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={disabled}
        className="text-sm text-sky-700 hover:underline disabled:opacity-60"
      >
        Указать свой диагноз
      </button>
    )
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
      <h4 className="font-medium text-slate-800 text-sm">
        Свой диагноз
      </h4>
      <label className="block">
        <span className="text-xs text-slate-600">Название</span>
        <input
          type="text"
          className="mt-0.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={disabled || busy}
        />
      </label>
      <label className="block">
        <span className="text-xs text-slate-600">МКБ-10 (опционально)</span>
        <input
          type="text"
          className="mt-0.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          value={icd}
          onChange={(e) => setIcd(e.target.value)}
          disabled={disabled || busy}
        />
      </label>
      <label className="block">
        <span className="text-xs text-slate-600">
          Причина несогласия (опционально)
        </span>
        <textarea
          className="mt-0.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={disabled || busy}
        />
      </label>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={!title.trim() || busy || disabled}
          className="rounded-md bg-slate-900 text-white px-3 py-1.5 text-sm font-medium hover:bg-slate-700 disabled:opacity-60"
        >
          Сохранить
        </button>
        <button
          type="button"
          onClick={() => {
            reset()
            setOpen(false)
          }}
          disabled={busy}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-white"
        >
          Отмена
        </button>
      </div>
    </div>
  )
}
