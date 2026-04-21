import { apiClient } from './client'

export type PatientSex = 'male' | 'female' | 'other'
export type AppointmentType = 'primary' | 'follow_up'
export type SessionStatus =
  | 'draft'
  | 'recording'
  | 'analyzed'
  | 'confirmed'
  | 'closed'
export type Speaker = 'doctor' | 'patient' | 'unknown'

export interface Transcript {
  id: string
  session_id: string
  speaker: Speaker
  text: string
  started_at_ms: number | null
  ended_at_ms: number | null
  confidence: number | null
  edited_by_user: boolean
  created_at: string
}

export interface AppointmentSession {
  id: string
  doctor_id: string
  patient_full_name: string
  patient_age: number
  patient_sex: PatientSex
  appointment_type: AppointmentType
  status: SessionStatus
  consent_given_at: string | null
  created_at: string
  updated_at: string
  final_diagnosis?: string | null
}

export interface SessionDetail extends AppointmentSession {
  transcripts: Transcript[]
}

export interface SessionListResponse {
  items: AppointmentSession[]
  total: number
  limit: number
  offset: number
}

export interface CreateSessionPayload {
  patient_full_name: string
  patient_age: number
  patient_sex: PatientSex
  appointment_type: AppointmentType
}

export interface ListSessionsParams {
  status?: SessionStatus | 'all'
  query?: string
  limit?: number
  offset?: number
}

export async function listSessions(
  params: ListSessionsParams = {},
): Promise<SessionListResponse> {
  const { data } = await apiClient.get<SessionListResponse>('/sessions', {
    params: {
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
      ...(params.status && params.status !== 'all'
        ? { status: params.status }
        : {}),
      ...(params.query && params.query.trim()
        ? { query: params.query.trim() }
        : {}),
    },
  })
  return data
}

export async function getSession(id: string): Promise<SessionDetail> {
  const { data } = await apiClient.get<SessionDetail>(`/sessions/${id}`)
  return data
}

export async function createSession(
  payload: CreateSessionPayload,
): Promise<AppointmentSession> {
  const { data } = await apiClient.post<AppointmentSession>(
    '/sessions',
    payload,
  )
  return data
}

export async function patchSession(
  id: string,
  payload: Partial<CreateSessionPayload>,
): Promise<AppointmentSession> {
  const { data } = await apiClient.patch<AppointmentSession>(
    `/sessions/${id}`,
    payload,
  )
  return data
}

export async function setConsent(
  id: string,
  granted: boolean,
): Promise<AppointmentSession> {
  const { data } = await apiClient.post<AppointmentSession>(
    `/sessions/${id}/consent`,
    { granted },
  )
  return data
}

export async function startRecording(
  id: string,
): Promise<AppointmentSession> {
  const { data } = await apiClient.post<AppointmentSession>(
    `/sessions/${id}/start-recording`,
  )
  return data
}

export async function stopRecording(id: string): Promise<AppointmentSession> {
  const { data } = await apiClient.post<AppointmentSession>(
    `/sessions/${id}/stop-recording`,
  )
  return data
}

export async function deleteAudio(id: string): Promise<AppointmentSession> {
  const { data } = await apiClient.delete<AppointmentSession>(
    `/sessions/${id}/audio`,
  )
  return data
}

export interface UploadChunkPayload {
  sessionId: string
  audio: Blob
  speaker: Speaker
  startedAtMs: number
  endedAtMs: number
}

export async function uploadTranscriptChunk(
  payload: UploadChunkPayload,
): Promise<Transcript | null> {
  const form = new FormData()
  const filename = `chunk-${payload.startedAtMs}.webm`
  form.append('audio', payload.audio, filename)
  form.append('speaker', payload.speaker)
  form.append('started_at_ms', String(payload.startedAtMs))
  form.append('ended_at_ms', String(payload.endedAtMs))
  const response = await apiClient.post<Transcript | ''>(
    `/sessions/${payload.sessionId}/transcripts`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  // 204 No Content = chunk was silence / recognized as a Whisper hallucination
  // and filtered out on the server. Nothing to append to the transcript.
  if (response.status === 204) return null
  return response.data as Transcript
}

export async function patchTranscript(
  sessionId: string,
  transcriptId: string,
  payload: { text?: string; speaker?: Speaker },
): Promise<Transcript> {
  const { data } = await apiClient.patch<Transcript>(
    `/sessions/${sessionId}/transcripts/${transcriptId}`,
    payload,
  )
  return data
}

export async function deleteTranscript(
  sessionId: string,
  transcriptId: string,
): Promise<void> {
  await apiClient.delete(`/sessions/${sessionId}/transcripts/${transcriptId}`)
}
