import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import {
  createSession,
  type AppointmentSession,
  type AppointmentType,
  type CreateSessionPayload,
  type PatientSex,
} from '../api/sessions'

interface ApiError {
  detail?: string
}

export function SessionCreatePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [fullName, setFullName] = useState('')
  const [age, setAge] = useState<string>('')
  const [sex, setSex] = useState<PatientSex>('male')
  const [appointmentType, setAppointmentType] =
    useState<AppointmentType>('primary')

  const mutation = useMutation<
    AppointmentSession,
    AxiosError<ApiError>,
    CreateSessionPayload
  >({
    mutationFn: createSession,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      navigate(`/app/sessions/${data.id}`, { replace: true })
    },
  })

  const handleSubmit = (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    const parsedAge = Number(age)
    if (!fullName.trim()) return
    if (!Number.isFinite(parsedAge) || parsedAge < 0 || parsedAge > 120) return
    mutation.mutate({
      patient_full_name: fullName.trim(),
      patient_age: Math.floor(parsedAge),
      patient_sex: sex,
      appointment_type: appointmentType,
    })
  }

  const errorText = mutation.isError
    ? mutation.error?.response?.data?.detail ??
      'Не удалось создать сессию. Проверьте данные.'
    : null

  return (
    <section className="max-w-xl mx-auto space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-slate-900">Новый приём</h1>
        <p className="text-sm text-slate-500">
          Заполните данные пациента перед началом приёма.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="bg-white border border-slate-200 rounded-xl p-6 space-y-5"
        noValidate
      >
        <label className="block">
          <span className="block text-sm font-medium text-slate-700 mb-1">
            ФИО пациента
          </span>
          <input
            type="text"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-300"
            disabled={mutation.isPending}
          />
        </label>

        <label className="block max-w-[8rem]">
          <span className="block text-sm font-medium text-slate-700 mb-1">
            Возраст
          </span>
          <input
            type="number"
            min={0}
            max={120}
            step={1}
            required
            value={age}
            onChange={(e) => setAge(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-300"
            disabled={mutation.isPending}
          />
        </label>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-slate-700 mb-1">
            Пол
          </legend>
          {(
            [
              ['male', 'Мужской'],
              ['female', 'Женский'],
              ['other', 'Другой'],
            ] as [PatientSex, string][]
          ).map(([value, label]) => (
            <label key={value} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="sex"
                value={value}
                checked={sex === value}
                onChange={() => setSex(value)}
              />
              {label}
            </label>
          ))}
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-slate-700 mb-1">
            Тип приёма
          </legend>
          {(
            [
              ['primary', 'Первичный'],
              ['follow_up', 'Повторный'],
            ] as [AppointmentType, string][]
          ).map(([value, label]) => (
            <label key={value} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="appointment_type"
                value={value}
                checked={appointmentType === value}
                onChange={() => setAppointmentType(value)}
              />
              {label}
            </label>
          ))}
        </fieldset>

        {errorText && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {errorText}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={
              mutation.isPending || !fullName.trim() || age === '' || Number(age) < 0
            }
            className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-5 py-2.5 text-white font-medium hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed transition"
          >
            {mutation.isPending ? 'Создаём…' : 'Создать'}
          </button>
          <Link
            to="/app"
            className="text-sm text-slate-600 hover:underline"
          >
            Отмена
          </Link>
        </div>
      </form>
    </section>
  )
}
