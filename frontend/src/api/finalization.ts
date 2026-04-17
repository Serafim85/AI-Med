import { apiClient } from './client'
import type {
  Protocol,
  RedFlagSeverity,
  TreatmentKind,
} from './analysis'
import type { AppointmentSession } from './sessions'

export interface DoctorInfo {
  id: string
  full_name: string
}

export interface SelectedDiagnosisInfo {
  title: string
  icd10_code: string | null
}

export interface RedFlagSummary {
  id: string
  label: string
  description: string | null
  severity: RedFlagSeverity | null
  acknowledged_at: string | null
  doctor_note: string | null
}

export interface TreatmentItemSummary {
  id: string
  kind: TreatmentKind
  title: string
  details: string | null
  dosage: string | null
  duration: string | null
  order_index: number
  is_confirmed: boolean
}

export interface SessionSummary {
  session: AppointmentSession
  doctor: DoctorInfo
  protocol: Protocol | null
  selected_diagnosis: SelectedDiagnosisInfo | null
  red_flags: RedFlagSummary[]
  treatment_plan_items: TreatmentItemSummary[]
}

export async function getSessionSummary(
  id: string,
): Promise<SessionSummary> {
  const { data } = await apiClient.get<SessionSummary>(
    `/sessions/${id}/summary`,
  )
  return data
}

export interface ConfirmSessionResponse {
  session: AppointmentSession
  protocol: Protocol
}

export async function confirmSession(
  id: string,
): Promise<ConfirmSessionResponse> {
  const { data } = await apiClient.post<ConfirmSessionResponse>(
    `/sessions/${id}/confirm`,
  )
  return data
}

export interface CloseSessionResponse {
  session: AppointmentSession
}

export async function closeSession(
  id: string,
): Promise<CloseSessionResponse> {
  const { data } = await apiClient.post<CloseSessionResponse>(
    `/sessions/${id}/close`,
  )
  return data
}

/** Downloads the protocol PDF as a binary blob and triggers a browser save. */
export async function downloadSessionPdf(
  id: string,
  filename?: string,
): Promise<void> {
  const resp = await apiClient.get(`/sessions/${id}/pdf`, {
    responseType: 'blob',
  })
  const blob = new Blob([resp.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename ?? `protocol_${id}.pdf`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // Defer revoke so the browser finishes triggering the download.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
