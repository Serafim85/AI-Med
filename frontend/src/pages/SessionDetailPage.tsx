import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  deleteAudio,
  deleteTranscript,
  getSession,
  patchTranscript,
  setConsent,
  startRecording,
  stopRecording,
  uploadTranscriptChunk,
  type SessionDetail,
  type Speaker,
  type Transcript,
} from '../api/sessions'
import { AnalysisSection } from '../components/analysis/AnalysisSection'
import { TranscriptItem } from '../components/TranscriptItem'
import { useAudioRecorder } from '../hooks/useAudioRecorder'
import {
  APPOINTMENT_TYPE_LABEL,
  SEX_LABEL,
  SPEAKER_BADGE,
  SPEAKER_LABEL,
  STATUS_BADGE,
  STATUS_LABEL,
  formatDate,
  formatDurationMs,
} from '../lib/formatters'
import { useSessionStore } from '../store/session'

interface ApiError {
  detail?: string
}

const CONSENT_TEXT = `Добрый день! Я хочу сделать аудиозапись нашего приёма, чтобы не упустить деталей и помочь вам точнее. Запись используется только для подготовки медицинского протокола и не передаётся третьим лицам. Вы согласны на запись?`

export function SessionDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const setActiveSession = useSessionStore((s) => s.setActiveSession)
  const currentSpeaker = useSessionStore((s) => s.currentSpeaker)
  const setCurrentSpeaker = useSessionStore((s) => s.setCurrentSpeaker)
  const recorderStatus = useSessionStore((s) => s.recorderStatus)
  const durationMs = useSessionStore((s) => s.durationMs)
  const soundLevel = useSessionStore((s) => s.soundLevel)
  const pendingChunks = useSessionStore((s) => s.pendingChunks)
  const addPendingChunk = useSessionStore((s) => s.addPendingChunk)
  const updatePendingChunk = useSessionStore((s) => s.updatePendingChunk)
  const removePendingChunk = useSessionStore((s) => s.removePendingChunk)
  const resetRecordingState = useSessionStore((s) => s.resetRecordingState)

  const [consentRead, setConsentRead] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)

  useEffect(() => {
    setActiveSession(id)
    return () => setActiveSession(null)
  }, [id, setActiveSession])

  const { data: session, isLoading, isError, refetch } =
    useQuery<SessionDetail>({
      queryKey: ['session', id],
      queryFn: () => getSession(id),
      enabled: !!id,
    })

  // Mutations
  const consentMutation = useMutation({
    mutationFn: (granted: boolean) => setConsent(id, granted),
    onSuccess: (data) => {
      queryClient.setQueryData<SessionDetail>(['session', id], (prev) =>
        prev ? { ...prev, ...data } : prev,
      )
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
    onError: (err: AxiosError<ApiError>) => {
      // "granted: false" returns 400 — this means the doctor denied; go back.
      if (err.response?.status === 400) {
        navigate('/app', { replace: true })
      }
    },
  })

  const startMutation = useMutation({
    mutationFn: () => startRecording(id),
    onSuccess: (data) => {
      queryClient.setQueryData<SessionDetail>(['session', id], (prev) =>
        prev ? { ...prev, ...data } : prev,
      )
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => stopRecording(id),
    onSuccess: (data) => {
      queryClient.setQueryData<SessionDetail>(['session', id], (prev) =>
        prev ? { ...prev, ...data } : prev,
      )
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const deleteAudioMutation = useMutation({
    mutationFn: () => deleteAudio(id),
    onSuccess: (data) => {
      queryClient.setQueryData<SessionDetail>(['session', id], (prev) =>
        prev ? { ...prev, ...data, transcripts: [] } : prev,
      )
      resetRecordingState()
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const patchTranscriptMutation = useMutation({
    mutationFn: (args: {
      transcriptId: string
      patch: { text?: string; speaker?: Speaker }
    }) => patchTranscript(id, args.transcriptId, args.patch),
    onSuccess: (updated) => {
      queryClient.setQueryData<SessionDetail>(['session', id], (prev) =>
        prev
          ? {
              ...prev,
              transcripts: prev.transcripts.map((t) =>
                t.id === updated.id ? updated : t,
              ),
            }
          : prev,
      )
    },
  })

  const deleteTranscriptMutation = useMutation({
    mutationFn: (transcriptId: string) => deleteTranscript(id, transcriptId),
    onSuccess: (_, transcriptId) => {
      queryClient.setQueryData<SessionDetail>(['session', id], (prev) =>
        prev
          ? {
              ...prev,
              transcripts: prev.transcripts.filter(
                (t) => t.id !== transcriptId,
              ),
            }
          : prev,
      )
    },
  })

  const appendTranscriptToCache = useCallback(
    (t: Transcript) => {
      queryClient.setQueryData<SessionDetail>(['session', id], (prev) =>
        prev ? { ...prev, transcripts: [...prev.transcripts, t] } : prev,
      )
    },
    [id, queryClient],
  )

  const recorder = useAudioRecorder({
    onChunk: async ({ audio, startedAtMs, endedAtMs }) => {
      const clientId = `chunk-${startedAtMs}-${Math.random()
        .toString(36)
        .slice(2, 8)}`
      const speaker = useSessionStore.getState().currentSpeaker
      addPendingChunk({
        clientId,
        speaker,
        startedAtMs,
        endedAtMs,
        status: 'uploading',
      })
      try {
        const transcript = await uploadTranscriptChunk({
          sessionId: id,
          audio,
          speaker,
          startedAtMs,
          endedAtMs,
        })
        if (transcript) {
          appendTranscriptToCache(transcript)
        }
        // `transcript === null` means the server detected silence/noise and
        // did not create a row — just drop the pending placeholder.
        removePendingChunk(clientId)
      } catch (err) {
        const message =
          (err as AxiosError<ApiError>)?.response?.data?.detail ??
          'Ошибка отправки чанка'
        updatePendingChunk(clientId, { status: 'error', error: message })
      }
    },
    onError: (err) => {
      setMicError(err.message)
    },
  })

  const handleStartRecording = async () => {
    setMicError(null)
    try {
      await startMutation.mutateAsync()
      await recorder.start()
    } catch (err) {
      const message =
        (err as Error).message ?? 'Не удалось начать запись'
      setMicError(message)
    }
  }

  const handleStopRecording = async () => {
    try {
      await recorder.stop()
    } finally {
      await stopMutation.mutateAsync().catch(() => undefined)
    }
  }

  const handleDeleteAudio = async () => {
    if (
      !window.confirm(
        'Удалить все распознанные реплики этой сессии? Это действие нельзя отменить.',
      )
    ) {
      return
    }
    try {
      await recorder.stop()
    } catch {
      /* ignore */
    }
    await deleteAudioMutation.mutateAsync().catch(() => undefined)
  }

  if (isLoading) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-slate-500">
        Загрузка…
      </div>
    )
  }

  if (isError || !session) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-6 space-y-3">
        <p>Не удалось открыть сессию. Возможно, она не существует.</p>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded border border-red-300 px-3 py-1 hover:bg-red-100"
        >
          Повторить
        </button>
        <Link to="/app" className="block text-sm underline">
          Назад к списку
        </Link>
      </div>
    )
  }

  const hasConsent = session.consent_given_at !== null
  const isRecording = recorderStatus === 'recording'
  const isPaused = recorderStatus === 'paused'
  const recorderBusy =
    recorderStatus === 'recording' || recorderStatus === 'stopping'
  const recordingPhaseActive =
    session.status === 'draft' || session.status === 'recording'

  return (
    <section className="space-y-6">
      <header className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">
              Приём от {formatDate(session.created_at)}
            </div>
            <h1 className="text-xl font-semibold text-slate-900">
              {session.patient_full_name}
            </h1>
            <p className="text-sm text-slate-600">
              {session.patient_age} лет · {SEX_LABEL[session.patient_sex]} ·{' '}
              {APPOINTMENT_TYPE_LABEL[session.appointment_type]}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span
              className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${STATUS_BADGE[session.status]}`}
            >
              {STATUS_LABEL[session.status]}
            </span>
            <Link to="/app" className="text-xs text-slate-500 hover:underline">
              ← К списку
            </Link>
          </div>
        </div>
      </header>

      {!hasConsent && (
        <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
          <h2 className="text-lg font-semibold text-slate-900">
            Согласие на аудиозапись
          </h2>
          <p className="text-sm text-slate-700 whitespace-pre-wrap rounded-lg bg-slate-50 border border-slate-200 p-3">
            {CONSENT_TEXT}
          </p>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={consentRead}
              onChange={(e) => setConsentRead(e.target.checked)}
            />
            Зачитал(а) пациенту
          </label>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => consentMutation.mutate(true)}
              disabled={!consentRead || consentMutation.isPending}
              className="inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-60 disabled:cursor-not-allowed transition"
            >
              Согласие получено
            </button>
            <button
              type="button"
              onClick={() => consentMutation.mutate(false)}
              disabled={consentMutation.isPending}
              className="inline-flex items-center justify-center rounded-lg border border-red-300 text-red-700 px-4 py-2 text-sm font-medium hover:bg-red-50 transition"
            >
              Отказ
            </button>
          </div>
        </section>
      )}

      {hasConsent && (
        <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-slate-900">
              Запись приёма
            </h2>
            <div className="text-sm text-slate-500">
              Длительность: {formatDurationMs(durationMs)}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {recordingPhaseActive && (
              <div className="inline-flex rounded-lg border border-slate-200 overflow-hidden text-sm">
                {(
                  [
                    ['doctor', 'Врач'],
                    ['patient', 'Пациент'],
                  ] as [Speaker, string][]
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={`px-3 py-1.5 ${
                      currentSpeaker === value
                        ? 'bg-slate-900 text-white'
                        : 'bg-white text-slate-700 hover:bg-slate-100'
                    }`}
                    onClick={() => setCurrentSpeaker(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}

            {recordingPhaseActive && !isRecording && !isPaused && (
              <button
                type="button"
                onClick={handleStartRecording}
                disabled={
                  startMutation.isPending ||
                  recorderStatus === 'stopping' ||
                  session.status === 'closed'
                }
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-white text-sm font-medium hover:bg-red-500 disabled:opacity-60 disabled:cursor-not-allowed transition"
              >
                <span className="inline-block w-2 h-2 rounded-full bg-white" />
                Начать запись
              </button>
            )}

            {recordingPhaseActive && isRecording && (
              <>
                <button
                  type="button"
                  onClick={() => recorder.pause()}
                  className="inline-flex items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100"
                >
                  Пауза
                </button>
                <button
                  type="button"
                  onClick={handleStopRecording}
                  className="inline-flex items-center justify-center rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-medium hover:bg-slate-700"
                >
                  Остановить
                </button>
              </>
            )}

            {recordingPhaseActive && isPaused && (
              <>
                <button
                  type="button"
                  onClick={() => recorder.resume()}
                  className="inline-flex items-center justify-center rounded-lg bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-500"
                >
                  Продолжить
                </button>
                <button
                  type="button"
                  onClick={handleStopRecording}
                  className="inline-flex items-center justify-center rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-medium hover:bg-slate-700"
                >
                  Остановить
                </button>
              </>
            )}

            <div className="ml-auto flex items-center gap-2 min-w-[120px]">
              <span className="text-xs text-slate-500">Звук</span>
              <div className="relative h-2 w-28 rounded-full bg-slate-200 overflow-hidden">
                <div
                  className="absolute left-0 top-0 bottom-0 bg-emerald-500 transition-[width] duration-75"
                  style={{
                    width: `${Math.round(Math.min(1, soundLevel) * 100)}%`,
                  }}
                />
              </div>
            </div>
          </div>

          {micError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {micError}. Проверьте разрешение на микрофон в настройках
              браузера и попробуйте снова.
            </div>
          )}

          <div>
            <h3 className="text-sm font-medium text-slate-700 mb-2">
              Расшифровка ({session.transcripts.length + pendingChunks.length})
            </h3>
            {session.transcripts.length === 0 && pendingChunks.length === 0 ? (
              <p className="text-sm text-slate-500 italic">
                Реплик ещё нет. Начните запись, чтобы увидеть расшифровку.
              </p>
            ) : (
              <ul className="space-y-2">
                {session.transcripts.map((t) => (
                  <TranscriptItem
                    key={t.id}
                    transcript={t}
                    onEdit={(tid, patch) =>
                      patchTranscriptMutation.mutate({
                        transcriptId: tid,
                        patch,
                      })
                    }
                    onDelete={(tid) => deleteTranscriptMutation.mutate(tid)}
                    busy={
                      patchTranscriptMutation.isPending ||
                      deleteTranscriptMutation.isPending
                    }
                  />
                ))}
                {pendingChunks.map((c) => (
                  <li
                    key={c.clientId}
                    className={`border rounded-xl p-3 text-sm ${
                      c.status === 'error'
                        ? 'border-red-200 bg-red-50 text-red-700'
                        : 'border-dashed border-slate-300 bg-slate-50 text-slate-500'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1 text-xs">
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 font-medium ${SPEAKER_BADGE[c.speaker]}`}
                      >
                        {SPEAKER_LABEL[c.speaker]}
                      </span>
                      <span>
                        {formatDurationMs(c.startedAtMs)} –{' '}
                        {formatDurationMs(c.endedAtMs)}
                      </span>
                    </div>
                    {c.status === 'uploading' ? (
                      <span>Распознаём…</span>
                    ) : (
                      <span>{c.error ?? 'Ошибка распознавания'}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {hasConsent && session.transcripts.length > 0 && session.status === 'draft' && (
        <section className="bg-white border border-slate-200 rounded-xl p-5">
          <button
            type="button"
            onClick={handleDeleteAudio}
            disabled={deleteAudioMutation.isPending || recorderBusy}
            className="inline-flex items-center justify-center rounded-lg border border-red-300 text-red-700 px-4 py-2 text-sm font-medium hover:bg-red-50 disabled:opacity-60 disabled:cursor-not-allowed transition"
          >
            Удалить запись
          </button>
          <p className="text-xs text-slate-500 mt-2">
            Удалит все распознанные реплики этой сессии и вернёт её в черновик.
          </p>
        </section>
      )}

      <AnalysisSection sessionId={id} session={session} />
    </section>
  )
}
