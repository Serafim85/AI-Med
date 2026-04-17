import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { useNavigate } from 'react-router-dom'

import {
  acknowledgeRedFlag,
  analyzeSession,
  createPlanItem,
  deletePlanItem,
  getAnalysis,
  patchPlanItem,
  patchProtocol,
  reorderPlanItems,
  selectDiagnosis,
  setCustomDiagnosis,
  type AnalysisResponse,
  type CreatePlanItemPayload,
  type CustomDiagnosisPayload,
  type PatchPlanItemPayload,
  type ProtocolPatchPayload,
} from '../../api/analysis'
import type { SessionDetail } from '../../api/sessions'
import { DiagnosesPanel } from './DiagnosesPanel'
import { ProtocolPanel } from './ProtocolPanel'
import { RedFlagsPanel } from './RedFlagsPanel'
import { TreatmentPlanPanel } from './TreatmentPlanPanel'

interface ApiError {
  detail?: string
}

function extractDetail(err: unknown, fallback: string): string {
  const axe = err as AxiosError<ApiError>
  return axe?.response?.data?.detail ?? fallback
}

interface Props {
  sessionId: string
  session: SessionDetail
}

/** Status in which the analysis card is visible & read/writable. */
const ANALYSIS_STATUSES: SessionDetail['status'][] = [
  'analyzed',
  'confirmed',
  'closed',
]

export function AnalysisSection({ sessionId, session }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const analysisEnabled = ANALYSIS_STATUSES.includes(session.status)
  const canEdit = session.status === 'analyzed'

  const analysisQuery = useQuery<AnalysisResponse>({
    queryKey: ['analysis', sessionId],
    queryFn: () => getAnalysis(sessionId),
    enabled: analysisEnabled,
  })

  const invalidateSessionAndAnalysis = () => {
    queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
    queryClient.invalidateQueries({ queryKey: ['analysis', sessionId] })
  }

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeSession(sessionId),
    onSuccess: (data) => {
      queryClient.setQueryData(['analysis', sessionId], data)
      invalidateSessionAndAnalysis()
    },
  })

  const protocolMutation = useMutation({
    mutationFn: (payload: ProtocolPatchPayload) =>
      patchProtocol(sessionId, payload),
    onSuccess: (protocol) => {
      queryClient.setQueryData<AnalysisResponse | undefined>(
        ['analysis', sessionId],
        (prev) => (prev ? { ...prev, protocol } : prev),
      )
    },
  })

  const selectMutation = useMutation({
    mutationFn: (suggestionId: string) =>
      selectDiagnosis(sessionId, suggestionId),
    onSuccess: (protocol, suggestionId) => {
      queryClient.setQueryData<AnalysisResponse | undefined>(
        ['analysis', sessionId],
        (prev) =>
          prev
            ? {
                ...prev,
                protocol,
                diagnosis_suggestions: prev.diagnosis_suggestions.map((s) => ({
                  ...s,
                  is_selected: s.id === suggestionId,
                })),
              }
            : prev,
      )
    },
  })

  const customDiagnosisMutation = useMutation({
    mutationFn: (payload: CustomDiagnosisPayload) =>
      setCustomDiagnosis(sessionId, payload),
    onSuccess: (protocol) => {
      queryClient.setQueryData<AnalysisResponse | undefined>(
        ['analysis', sessionId],
        (prev) =>
          prev
            ? {
                ...prev,
                protocol,
                diagnosis_suggestions: prev.diagnosis_suggestions.map((s) => ({
                  ...s,
                  is_selected: false,
                })),
              }
            : prev,
      )
    },
  })

  const acknowledgeMutation = useMutation({
    mutationFn: (args: {
      id: string
      payload: { accepted: boolean; note?: string | null }
    }) => acknowledgeRedFlag(sessionId, args.id, args.payload),
    onSuccess: (updated) => {
      queryClient.setQueryData<AnalysisResponse | undefined>(
        ['analysis', sessionId],
        (prev) =>
          prev
            ? {
                ...prev,
                red_flags: prev.red_flags.map((rf) =>
                  rf.id === updated.id ? updated : rf,
                ),
              }
            : prev,
      )
    },
  })

  const createItemMutation = useMutation({
    mutationFn: (payload: CreatePlanItemPayload) =>
      createPlanItem(sessionId, payload),
    onSuccess: (created) => {
      queryClient.setQueryData<AnalysisResponse | undefined>(
        ['analysis', sessionId],
        (prev) =>
          prev && prev.treatment_plan
            ? {
                ...prev,
                treatment_plan: {
                  ...prev.treatment_plan,
                  items: [...prev.treatment_plan.items, created],
                },
              }
            : prev,
      )
    },
  })

  const patchItemMutation = useMutation({
    mutationFn: (args: { itemId: string; payload: PatchPlanItemPayload }) =>
      patchPlanItem(sessionId, args.itemId, args.payload),
    onSuccess: (updated) => {
      queryClient.setQueryData<AnalysisResponse | undefined>(
        ['analysis', sessionId],
        (prev) =>
          prev && prev.treatment_plan
            ? {
                ...prev,
                treatment_plan: {
                  ...prev.treatment_plan,
                  items: prev.treatment_plan.items.map((i) =>
                    i.id === updated.id ? updated : i,
                  ),
                },
              }
            : prev,
      )
    },
  })

  const deleteItemMutation = useMutation({
    mutationFn: (itemId: string) => deletePlanItem(sessionId, itemId),
    onSuccess: (_v, itemId) => {
      queryClient.setQueryData<AnalysisResponse | undefined>(
        ['analysis', sessionId],
        (prev) =>
          prev && prev.treatment_plan
            ? {
                ...prev,
                treatment_plan: {
                  ...prev.treatment_plan,
                  items: prev.treatment_plan.items.filter(
                    (i) => i.id !== itemId,
                  ),
                },
              }
            : prev,
      )
    },
  })

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: string[]) =>
      reorderPlanItems(sessionId, orderedIds),
    onSuccess: (plan) => {
      queryClient.setQueryData<AnalysisResponse | undefined>(
        ['analysis', sessionId],
        (prev) => (prev ? { ...prev, treatment_plan: plan } : prev),
      )
    },
  })

  const handleAnalyze = async () => {
    try {
      await analyzeMutation.mutateAsync()
    } catch (err) {
      alert(extractDetail(err, 'Не удалось выполнить анализ'))
    }
  }

  const handleReAnalyze = async () => {
    if (
      !window.confirm(
        'Повторный анализ перезапишет все предложения LLM. Ваши ручные правки протокола и плана могут быть потеряны. Продолжить?',
      )
    ) {
      return
    }
    await handleAnalyze()
  }

  const analyzeError = analyzeMutation.error
    ? extractDetail(analyzeMutation.error, 'Ошибка анализа')
    : null

  // ---- UI ----

  if (session.status === 'draft') {
    if (session.transcripts.length === 0) {
      return null
    }
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
        <h3 className="text-lg font-semibold text-slate-900">
          Готово к анализу
        </h3>
        <p className="text-sm text-slate-600">
          Транскрипт собран. Запустите AI-анализ, чтобы получить черновик
          протокола, топ-3 диагноза, красные флаги и план лечения.
        </p>
        <button
          type="button"
          onClick={handleAnalyze}
          disabled={analyzeMutation.isPending}
          className="rounded-lg bg-sky-600 text-white px-4 py-2 text-sm font-medium hover:bg-sky-500 disabled:opacity-60"
        >
          {analyzeMutation.isPending ? 'Идёт анализ диалога…' : 'Анализировать'}
        </button>
        {analyzeError && (
          <div className="rounded-md border border-red-200 bg-red-50 text-red-700 text-sm px-3 py-2">
            {analyzeError}
          </div>
        )}
      </section>
    )
  }

  if (!analysisEnabled) return null

  if (analysisQuery.isLoading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500 text-center">
        Загрузка анализа…
      </div>
    )
  }
  if (analysisQuery.isError || !analysisQuery.data) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-700 text-sm">
        Не удалось загрузить анализ.{' '}
        <button
          type="button"
          onClick={() => analysisQuery.refetch()}
          className="underline"
        >
          Повторить
        </button>
      </div>
    )
  }

  const analysis = analysisQuery.data
  const plan = analysis.treatment_plan
  const reAnalyzing = analyzeMutation.isPending

  return (
    <>
      {reAnalyzing && (
        <div className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
          Идёт анализ диалога…
        </div>
      )}

      <RedFlagsPanel
        redFlags={analysis.red_flags}
        disabled={!canEdit}
        onAcknowledge={async (id, payload) => {
          try {
            await acknowledgeMutation.mutateAsync({ id, payload })
          } catch (err) {
            alert(extractDetail(err, 'Не удалось обновить флаг'))
          }
        }}
      />

      {analysis.protocol && (
        <ProtocolPanel
          protocol={analysis.protocol}
          disabled={!canEdit}
          onPatch={async (payload) => {
            try {
              await protocolMutation.mutateAsync(payload)
            } catch (err) {
              alert(extractDetail(err, 'Не удалось сохранить протокол'))
            }
          }}
        />
      )}

      <DiagnosesPanel
        suggestions={analysis.diagnosis_suggestions}
        disabled={!canEdit}
        onSelect={async (sid) => {
          try {
            await selectMutation.mutateAsync(sid)
          } catch (err) {
            alert(extractDetail(err, 'Не удалось выбрать диагноз'))
          }
        }}
        onCustom={async (payload) => {
          try {
            await customDiagnosisMutation.mutateAsync(payload)
          } catch (err) {
            alert(extractDetail(err, 'Не удалось сохранить свой диагноз'))
          }
        }}
      />

      <TreatmentPlanPanel
        items={plan?.items ?? []}
        disabled={!canEdit}
        onCreate={async (payload) => {
          try {
            await createItemMutation.mutateAsync(payload)
          } catch (err) {
            alert(extractDetail(err, 'Не удалось добавить пункт'))
          }
        }}
        onPatch={async (itemId, payload) => {
          try {
            await patchItemMutation.mutateAsync({ itemId, payload })
          } catch (err) {
            alert(extractDetail(err, 'Не удалось обновить пункт'))
          }
        }}
        onDelete={async (itemId) => {
          try {
            await deleteItemMutation.mutateAsync(itemId)
          } catch (err) {
            alert(extractDetail(err, 'Не удалось удалить пункт'))
          }
        }}
        onReorder={async (orderedIds) => {
          try {
            await reorderMutation.mutateAsync(orderedIds)
          } catch (err) {
            alert(extractDetail(err, 'Не удалось изменить порядок'))
          }
        }}
      />

      <section className="rounded-xl border border-slate-200 bg-white p-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() =>
            navigate(`/app/sessions/${sessionId}/confirm`)
          }
          className="rounded-lg bg-emerald-600 text-white px-4 py-2 text-sm font-medium hover:bg-emerald-500"
        >
          К итоговому протоколу
        </button>
        {canEdit && (
          <button
            type="button"
            onClick={handleReAnalyze}
            disabled={reAnalyzing}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-60"
          >
            Перезапустить анализ
          </button>
        )}
        {analyzeError && (
          <div className="w-full rounded-md border border-red-200 bg-red-50 text-red-700 text-sm px-3 py-2">
            {analyzeError}
          </div>
        )}
      </section>
    </>
  )
}
