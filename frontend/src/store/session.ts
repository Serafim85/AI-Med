import { create } from 'zustand'

import type { Speaker } from '../api/sessions'

export type RecorderStatus = 'idle' | 'recording' | 'paused' | 'stopping'

export interface PendingChunk {
  clientId: string
  speaker: Speaker
  startedAtMs: number
  endedAtMs: number
  status: 'uploading' | 'error'
  error?: string
}

interface SessionState {
  activeSessionId: string | null
  currentSpeaker: Speaker
  recorderStatus: RecorderStatus
  /** Cumulative recording duration in ms. */
  durationMs: number
  /** Sound level in [0, 1] driven by AudioWorklet/AnalyserNode. */
  soundLevel: number
  pendingChunks: PendingChunk[]

  setActiveSession: (id: string | null) => void
  setCurrentSpeaker: (speaker: Speaker) => void
  setRecorderStatus: (status: RecorderStatus) => void
  setDurationMs: (ms: number) => void
  setSoundLevel: (level: number) => void
  addPendingChunk: (chunk: PendingChunk) => void
  updatePendingChunk: (clientId: string, patch: Partial<PendingChunk>) => void
  removePendingChunk: (clientId: string) => void
  resetRecordingState: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  activeSessionId: null,
  currentSpeaker: 'doctor',
  recorderStatus: 'idle',
  durationMs: 0,
  soundLevel: 0,
  pendingChunks: [],

  setActiveSession: (id) =>
    set((state) =>
      state.activeSessionId === id
        ? state
        : {
            activeSessionId: id,
            recorderStatus: 'idle',
            durationMs: 0,
            soundLevel: 0,
            pendingChunks: [],
          },
    ),
  setCurrentSpeaker: (speaker) => set({ currentSpeaker: speaker }),
  setRecorderStatus: (status) => set({ recorderStatus: status }),
  setDurationMs: (ms) => set({ durationMs: ms }),
  setSoundLevel: (level) => set({ soundLevel: level }),
  addPendingChunk: (chunk) =>
    set((s) => ({ pendingChunks: [...s.pendingChunks, chunk] })),
  updatePendingChunk: (clientId, patch) =>
    set((s) => ({
      pendingChunks: s.pendingChunks.map((c) =>
        c.clientId === clientId ? { ...c, ...patch } : c,
      ),
    })),
  removePendingChunk: (clientId) =>
    set((s) => ({
      pendingChunks: s.pendingChunks.filter((c) => c.clientId !== clientId),
    })),
  resetRecordingState: () =>
    set({
      recorderStatus: 'idle',
      durationMs: 0,
      soundLevel: 0,
      pendingChunks: [],
    }),
}))
