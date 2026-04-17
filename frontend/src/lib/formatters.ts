import type {
  AppointmentType,
  PatientSex,
  SessionStatus,
  Speaker,
} from '../api/sessions'

export const SEX_LABEL: Record<PatientSex, string> = {
  male: 'Мужской',
  female: 'Женский',
  other: 'Другой',
}

export const APPOINTMENT_TYPE_LABEL: Record<AppointmentType, string> = {
  primary: 'Первичный',
  follow_up: 'Повторный',
}

export const STATUS_LABEL: Record<SessionStatus, string> = {
  draft: 'Черновик',
  recording: 'Идёт запись',
  analyzed: 'Обработан',
  confirmed: 'Подтверждён',
  closed: 'Закрыт',
}

export const STATUS_BADGE: Record<SessionStatus, string> = {
  draft: 'bg-slate-100 text-slate-700 border-slate-200',
  recording: 'bg-red-50 text-red-700 border-red-200',
  analyzed: 'bg-amber-50 text-amber-700 border-amber-200',
  confirmed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  closed: 'bg-slate-100 text-slate-500 border-slate-200',
}

export const SPEAKER_LABEL: Record<Speaker, string> = {
  doctor: 'Врач',
  patient: 'Пациент',
  unknown: 'Неизвестно',
}

export const SPEAKER_BADGE: Record<Speaker, string> = {
  doctor: 'bg-sky-50 text-sky-700 border-sky-200',
  patient: 'bg-violet-50 text-violet-700 border-violet-200',
  unknown: 'bg-slate-100 text-slate-600 border-slate-200',
}

export function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function formatDurationMs(ms: number): string {
  const totalSec = Math.floor(Math.max(0, ms) / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function formatChunkTimestamp(ms: number | null): string {
  if (ms == null) return '—'
  return formatDurationMs(ms)
}
