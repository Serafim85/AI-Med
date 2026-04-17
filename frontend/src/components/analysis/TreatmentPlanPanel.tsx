import { useMemo, useState } from 'react'

import type {
  CreatePlanItemPayload,
  PatchPlanItemPayload,
  TreatmentKind,
  TreatmentPlanItem,
} from '../../api/analysis'
import {
  TREATMENT_KIND_LABEL,
  TREATMENT_KIND_ORDER,
} from '../../lib/formatters'

interface Props {
  items: TreatmentPlanItem[]
  disabled: boolean
  onCreate: (payload: CreatePlanItemPayload) => Promise<void> | void
  onPatch: (itemId: string, payload: PatchPlanItemPayload) => Promise<void> | void
  onDelete: (itemId: string) => Promise<void> | void
  onReorder: (orderedIds: string[]) => Promise<void> | void
}

export function TreatmentPlanPanel({
  items,
  disabled,
  onCreate,
  onPatch,
  onDelete,
  onReorder,
}: Props) {
  const [addOpen, setAddOpen] = useState(false)

  const sorted = useMemo(
    () => [...items].sort((a, b) => a.order_index - b.order_index),
    [items],
  )

  const moveItem = (itemId: string, direction: -1 | 1) => {
    const idx = sorted.findIndex((i) => i.id === itemId)
    if (idx === -1) return
    const swapIdx = idx + direction
    if (swapIdx < 0 || swapIdx >= sorted.length) return
    const next = [...sorted]
    const [taken] = next.splice(idx, 1)
    next.splice(swapIdx, 0, taken)
    onReorder(next.map((i) => i.id))
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-slate-900">План лечения</h3>
        <button
          type="button"
          onClick={() => setAddOpen(true)}
          disabled={disabled}
          className="rounded-md bg-slate-900 text-white px-3 py-1.5 text-sm font-medium hover:bg-slate-700 disabled:opacity-60"
        >
          + Добавить пункт
        </button>
      </div>

      {addOpen && (
        <AddItemForm
          disabled={disabled}
          onSubmit={async (payload) => {
            await onCreate(payload)
            setAddOpen(false)
          }}
          onCancel={() => setAddOpen(false)}
        />
      )}

      {TREATMENT_KIND_ORDER.map((kind) => {
        const group = sorted.filter((i) => i.kind === kind)
        if (group.length === 0) return null
        return (
          <div key={kind} className="space-y-2">
            <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
              {TREATMENT_KIND_LABEL[kind]}
            </h4>
            {group.map((item) => (
              <PlanItemCard
                key={item.id}
                item={item}
                disabled={disabled}
                canMoveUp={sorted.findIndex((i) => i.id === item.id) > 0}
                canMoveDown={
                  sorted.findIndex((i) => i.id === item.id) < sorted.length - 1
                }
                onMoveUp={() => moveItem(item.id, -1)}
                onMoveDown={() => moveItem(item.id, 1)}
                onPatch={(p) => onPatch(item.id, p)}
                onDelete={() => onDelete(item.id)}
              />
            ))}
          </div>
        )
      })}

      {sorted.length === 0 && !addOpen && (
        <p className="text-sm text-slate-500 italic">
          План пуст. Добавьте пункты вручную.
        </p>
      )}
    </section>
  )
}

function PlanItemCard({
  item,
  disabled,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
  onPatch,
  onDelete,
}: {
  item: TreatmentPlanItem
  disabled: boolean
  canMoveUp: boolean
  canMoveDown: boolean
  onMoveUp: () => void
  onMoveDown: () => void
  onPatch: (payload: PatchPlanItemPayload) => Promise<void> | void
  onDelete: () => Promise<void> | void
}) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)

  const toggleConfirm = async (checked: boolean) => {
    setBusy(true)
    try {
      await onPatch({ is_confirmed: checked })
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm('Удалить пункт плана?')) return
    setBusy(true)
    try {
      await onDelete()
    } finally {
      setBusy(false)
    }
  }

  if (editing) {
    return (
      <EditItemForm
        item={item}
        disabled={disabled}
        onSubmit={async (payload) => {
          setBusy(true)
          try {
            await onPatch(payload)
            setEditing(false)
          } finally {
            setBusy(false)
          }
        }}
        onCancel={() => setEditing(false)}
      />
    )
  }

  return (
    <div
      className={`rounded-lg border p-3 ${
        item.conflict
          ? 'border-amber-400 bg-amber-50'
          : 'border-slate-200 bg-white'
      }`}
    >
      {item.conflict && (
        <div className="mb-2 text-xs font-medium text-amber-800 bg-amber-100 border border-amber-200 rounded px-2 py-1">
          Внимание: возможный конфликт с аллергией/приёмом препаратов
        </div>
      )}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-slate-900">{item.title}</div>
          {item.details && (
            <div className="text-sm text-slate-700 mt-0.5">{item.details}</div>
          )}
          <div className="text-xs text-slate-500 mt-0.5 space-x-3">
            {item.dosage && <span>Доза: {item.dosage}</span>}
            {item.duration && <span>Длительность: {item.duration}</span>}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 text-xs">
          <label className="flex items-center gap-1.5 text-slate-700">
            <input
              type="checkbox"
              checked={item.is_confirmed}
              disabled={busy || disabled}
              onChange={(e) => toggleConfirm(e.target.checked)}
            />
            Подтверждено
          </label>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mt-2 text-xs">
        <button
          type="button"
          onClick={onMoveUp}
          disabled={!canMoveUp || disabled || busy}
          className="rounded border border-slate-300 px-2 py-0.5 text-slate-700 hover:bg-slate-100 disabled:opacity-40"
        >
          ↑
        </button>
        <button
          type="button"
          onClick={onMoveDown}
          disabled={!canMoveDown || disabled || busy}
          className="rounded border border-slate-300 px-2 py-0.5 text-slate-700 hover:bg-slate-100 disabled:opacity-40"
        >
          ↓
        </button>
        <button
          type="button"
          onClick={() => setEditing(true)}
          disabled={disabled || busy}
          className="rounded border border-slate-300 px-2 py-0.5 text-slate-700 hover:bg-slate-100 disabled:opacity-60"
        >
          Редактировать
        </button>
        <button
          type="button"
          onClick={handleDelete}
          disabled={disabled || busy}
          className="rounded border border-red-300 text-red-700 px-2 py-0.5 hover:bg-red-50 disabled:opacity-60"
        >
          Удалить
        </button>
      </div>
    </div>
  )
}

interface FormState {
  kind: TreatmentKind
  title: string
  details: string
  dosage: string
  duration: string
}

function AddItemForm({
  disabled,
  onSubmit,
  onCancel,
}: {
  disabled: boolean
  onSubmit: (payload: CreatePlanItemPayload) => Promise<void> | void
  onCancel: () => void
}) {
  const [state, setState] = useState<FormState>({
    kind: 'medication',
    title: '',
    details: '',
    dosage: '',
    duration: '',
  })
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!state.title.trim()) return
    setBusy(true)
    try {
      await onSubmit({
        kind: state.kind,
        title: state.title.trim(),
        details: state.details.trim() || null,
        dosage: state.dosage.trim() || null,
        duration: state.duration.trim() || null,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <PlanItemForm
      title="Новый пункт плана"
      state={state}
      setState={setState}
      disabled={disabled || busy}
      onSubmit={submit}
      onCancel={onCancel}
      submitLabel="Добавить"
    />
  )
}

function EditItemForm({
  item,
  disabled,
  onSubmit,
  onCancel,
}: {
  item: TreatmentPlanItem
  disabled: boolean
  onSubmit: (payload: PatchPlanItemPayload) => Promise<void> | void
  onCancel: () => void
}) {
  const [state, setState] = useState<FormState>({
    kind: item.kind,
    title: item.title,
    details: item.details ?? '',
    dosage: item.dosage ?? '',
    duration: item.duration ?? '',
  })
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!state.title.trim()) return
    setBusy(true)
    try {
      await onSubmit({
        kind: state.kind,
        title: state.title.trim(),
        details: state.details.trim() || null,
        dosage: state.dosage.trim() || null,
        duration: state.duration.trim() || null,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <PlanItemForm
      title="Редактирование пункта"
      state={state}
      setState={setState}
      disabled={disabled || busy}
      onSubmit={submit}
      onCancel={onCancel}
      submitLabel="Сохранить"
    />
  )
}

function PlanItemForm({
  title,
  state,
  setState,
  disabled,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  title: string
  state: FormState
  setState: (next: FormState) => void
  disabled: boolean
  onSubmit: () => void
  onCancel: () => void
  submitLabel: string
}) {
  return (
    <div className="rounded-lg border border-slate-300 bg-slate-50 p-4 space-y-3">
      <h4 className="font-medium text-slate-800 text-sm">{title}</h4>
      <label className="block">
        <span className="text-xs text-slate-600">Тип</span>
        <select
          className="mt-0.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm bg-white"
          value={state.kind}
          onChange={(e) =>
            setState({ ...state, kind: e.target.value as TreatmentKind })
          }
          disabled={disabled}
        >
          {TREATMENT_KIND_ORDER.map((kind) => (
            <option key={kind} value={kind}>
              {TREATMENT_KIND_LABEL[kind]}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="text-xs text-slate-600">Название</span>
        <input
          type="text"
          className="mt-0.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          value={state.title}
          onChange={(e) => setState({ ...state, title: e.target.value })}
          disabled={disabled}
        />
      </label>
      <label className="block">
        <span className="text-xs text-slate-600">Детали</span>
        <textarea
          className="mt-0.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          rows={2}
          value={state.details}
          onChange={(e) => setState({ ...state, details: e.target.value })}
          disabled={disabled}
        />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-xs text-slate-600">Дозировка</span>
          <input
            type="text"
            className="mt-0.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            value={state.dosage}
            onChange={(e) => setState({ ...state, dosage: e.target.value })}
            disabled={disabled}
          />
        </label>
        <label className="block">
          <span className="text-xs text-slate-600">Длительность</span>
          <input
            type="text"
            className="mt-0.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            value={state.duration}
            onChange={(e) => setState({ ...state, duration: e.target.value })}
            disabled={disabled}
          />
        </label>
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onSubmit}
          disabled={disabled || !state.title.trim()}
          className="rounded-md bg-slate-900 text-white px-3 py-1.5 text-sm font-medium hover:bg-slate-700 disabled:opacity-60"
        >
          {submitLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={disabled}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-white"
        >
          Отмена
        </button>
      </div>
    </div>
  )
}
