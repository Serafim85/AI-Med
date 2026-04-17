import { apiClient } from './client'
import type { AppointmentSession } from './sessions'

export type RedFlagSeverity = 'low' | 'medium' | 'high'
export type TreatmentKind =
  | 'medication'
  | 'investigation'
  | 'non_drug'
  | 'follow_up'

export interface Protocol {
  id: string
  session_id: string
  complaints: string
  anamnesis: string
  examination: string
  allergies: string
  medications: string
  final_diagnosis: string | null
  icd10_code: string | null
  confirmed_at: string | null
  created_at: string
  updated_at: string
}

export interface DiagnosisSuggestion {
  id: string
  session_id: string
  title: string
  icd10_code: string | null
  probability: number | null
  reasoning: string | null
  supporting_symptoms: string[]
  contradicting_symptoms: string[]
  is_selected: boolean
}

export interface RedFlag {
  id: string
  session_id: string
  label: string
  description: string | null
  severity: RedFlagSeverity | null
  acknowledged_at: string | null
  doctor_note: string | null
}

export interface TreatmentPlanItem {
  id: string
  plan_id: string
  kind: TreatmentKind
  title: string
  details: string | null
  dosage: string | null
  duration: string | null
  order_index: number
  is_confirmed: boolean
  conflict: boolean
}

export interface TreatmentPlan {
  id: string
  session_id: string
  items: TreatmentPlanItem[]
}

export interface AnalysisResponse {
  session: AppointmentSession
  protocol: Protocol | null
  diagnosis_suggestions: DiagnosisSuggestion[]
  red_flags: RedFlag[]
  treatment_plan: TreatmentPlan | null
}

export async function analyzeSession(id: string): Promise<AnalysisResponse> {
  const { data } = await apiClient.post<AnalysisResponse>(
    `/sessions/${id}/analyze`,
  )
  return data
}

export async function getAnalysis(id: string): Promise<AnalysisResponse> {
  const { data } = await apiClient.get<AnalysisResponse>(
    `/sessions/${id}/analysis`,
  )
  return data
}

export interface ProtocolPatchPayload {
  complaints?: string
  anamnesis?: string
  examination?: string
  allergies?: string
  medications?: string
  final_diagnosis?: string | null
  icd10_code?: string | null
}

export async function patchProtocol(
  id: string,
  payload: ProtocolPatchPayload,
): Promise<Protocol> {
  const { data } = await apiClient.patch<Protocol>(
    `/sessions/${id}/protocol`,
    payload,
  )
  return data
}

export async function selectDiagnosis(
  id: string,
  suggestionId: string,
): Promise<Protocol> {
  const { data } = await apiClient.post<Protocol>(
    `/sessions/${id}/diagnosis-suggestions/${suggestionId}/select`,
  )
  return data
}

export interface CustomDiagnosisPayload {
  title: string
  icd10_code?: string | null
  reason?: string | null
}

export async function setCustomDiagnosis(
  id: string,
  payload: CustomDiagnosisPayload,
): Promise<Protocol> {
  const { data } = await apiClient.post<Protocol>(
    `/sessions/${id}/protocol/custom-diagnosis`,
    payload,
  )
  return data
}

export async function acknowledgeRedFlag(
  id: string,
  redFlagId: string,
  payload: { accepted: boolean; note?: string | null },
): Promise<RedFlag> {
  const { data } = await apiClient.post<RedFlag>(
    `/sessions/${id}/red-flags/${redFlagId}/acknowledge`,
    payload,
  )
  return data
}

export interface CreatePlanItemPayload {
  kind: TreatmentKind
  title: string
  details?: string | null
  dosage?: string | null
  duration?: string | null
  order_index?: number | null
}

export async function createPlanItem(
  id: string,
  payload: CreatePlanItemPayload,
): Promise<TreatmentPlanItem> {
  const { data } = await apiClient.post<TreatmentPlanItem>(
    `/sessions/${id}/treatment-plan/items`,
    payload,
  )
  return data
}

export interface PatchPlanItemPayload {
  kind?: TreatmentKind
  title?: string
  details?: string | null
  dosage?: string | null
  duration?: string | null
  order_index?: number | null
  is_confirmed?: boolean
}

export async function patchPlanItem(
  id: string,
  itemId: string,
  payload: PatchPlanItemPayload,
): Promise<TreatmentPlanItem> {
  const { data } = await apiClient.patch<TreatmentPlanItem>(
    `/sessions/${id}/treatment-plan/items/${itemId}`,
    payload,
  )
  return data
}

export async function deletePlanItem(
  id: string,
  itemId: string,
): Promise<void> {
  await apiClient.delete(`/sessions/${id}/treatment-plan/items/${itemId}`)
}

export async function reorderPlanItems(
  id: string,
  orderedIds: string[],
): Promise<TreatmentPlan> {
  const { data } = await apiClient.post<TreatmentPlan>(
    `/sessions/${id}/treatment-plan/reorder`,
    { ordered_ids: orderedIds },
  )
  return data
}
