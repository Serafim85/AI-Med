import { useCallback, useEffect, useRef } from 'react'

import { useSessionStore } from '../store/session'

export interface ChunkPayload {
  audio: Blob
  startedAtMs: number
  endedAtMs: number
}

export interface RecorderHandlers {
  onChunk: (chunk: ChunkPayload) => Promise<void> | void
  onError?: (err: Error) => void
}

const CHUNK_INTERVAL_MS = 5000
const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
]

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  for (const mime of MIME_CANDIDATES) {
    try {
      if (MediaRecorder.isTypeSupported(mime)) return mime
    } catch {
      /* ignore */
    }
  }
  return undefined
}

/**
 * Low-level audio recorder hook. Delegates chunk handling to caller.
 *
 * Tracks:
 *  - cumulative duration in the Zustand store,
 *  - sound level via AnalyserNode (rAF polling),
 *  - per-chunk start/end offsets relative to the start of recording.
 *
 * Never holds chunks in memory past the moment they're passed to `onChunk`.
 */
export function useAudioRecorder(handlers: RecorderHandlers) {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const mimeTypeRef = useRef<string | undefined>(undefined)
  const rotateTimerRef = useRef<number | null>(null)
  // When false, `onstop` does NOT spin up a new recorder — used for pause/stop.
  const shouldRotateRef = useRef<boolean>(false)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const rafRef = useRef<number | null>(null)

  // timing
  const recStartRef = useRef<number>(0) // performance.now() of most recent (re)start
  const accumulatedRef = useRef<number>(0) // ms accumulated across pauses
  const chunkStartRef = useRef<number>(0) // relative ms where current chunk began
  const pauseAnchorRef = useRef<number | null>(null)

  const setRecorderStatus = useSessionStore((s) => s.setRecorderStatus)
  const setDurationMs = useSessionStore((s) => s.setDurationMs)
  const setSoundLevel = useSessionStore((s) => s.setSoundLevel)

  const stopMeter = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    setSoundLevel(0)
  }, [setSoundLevel])

  const clearRotateTimer = useCallback(() => {
    if (rotateTimerRef.current != null) {
      window.clearTimeout(rotateTimerRef.current)
      rotateTimerRef.current = null
    }
  }, [])

  const cleanup = useCallback(() => {
    shouldRotateRef.current = false
    clearRotateTimer()
    stopMeter()
    if (recorderRef.current) {
      try {
        if (recorderRef.current.state !== 'inactive') {
          recorderRef.current.stop()
        }
      } catch {
        /* ignore */
      }
      recorderRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => undefined)
      audioCtxRef.current = null
    }
    analyserRef.current = null
  }, [clearRotateTimer, stopMeter])

  useEffect(() => {
    return () => cleanup()
  }, [cleanup])

  const getElapsedMs = useCallback(() => {
    if (pauseAnchorRef.current != null) return accumulatedRef.current
    if (recStartRef.current === 0) return accumulatedRef.current
    return accumulatedRef.current + (performance.now() - recStartRef.current)
  }, [])

  const startMeter = useCallback(() => {
    const ctx = audioCtxRef.current
    const analyser = analyserRef.current
    if (!ctx || !analyser) return
    const data = new Uint8Array(analyser.fftSize)
    const tick = () => {
      analyser.getByteTimeDomainData(data)
      // RMS of samples centered at 128
      let sumSq = 0
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128
        sumSq += v * v
      }
      const rms = Math.sqrt(sumSq / data.length)
      setSoundLevel(Math.min(1, rms * 3))

      const dur = getElapsedMs()
      setDurationMs(Math.floor(dur))

      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [getElapsedMs, setDurationMs, setSoundLevel])

  // Creates a new MediaRecorder on the existing stream and starts it.
  // Each recorder lives for exactly one chunk (CHUNK_INTERVAL_MS) and then
  // is stop()'d, which flushes a complete, standalone WebM/Ogg file that
  // faster-whisper can decode. When `shouldRotateRef` is still true at the
  // moment of `onstop`, we immediately spin up the next recorder.
  const startRecorder = useCallback(() => {
    const stream = streamRef.current
    if (!stream) return
    const mimeType = mimeTypeRef.current
    const recorder = new MediaRecorder(
      stream,
      mimeType ? { mimeType } : undefined,
    )
    recorderRef.current = recorder

    recorder.ondataavailable = async (ev: BlobEvent) => {
      const blob = ev.data
      const endOffset = getElapsedMs()
      const startOffset = chunkStartRef.current
      chunkStartRef.current = endOffset
      if (!blob || blob.size === 0) return
      try {
        await handlersRef.current.onChunk({
          audio: blob,
          startedAtMs: Math.floor(startOffset),
          endedAtMs: Math.floor(endOffset),
        })
      } catch (err) {
        handlersRef.current.onError?.(
          err instanceof Error ? err : new Error(String(err)),
        )
      }
    }

    recorder.onstop = () => {
      if (shouldRotateRef.current) {
        // Start the next chunk immediately so there's minimal audio gap.
        startRecorder()
        scheduleRotation()
      }
    }

    recorder.onerror = (ev: Event) => {
      const err = new Error(
        (ev as Event & { error?: Error }).error?.message ??
          'Ошибка записи аудио',
      )
      handlersRef.current.onError?.(err)
    }

    // No timeslice: we want a single complete container per recorder.
    recorder.start()
  }, [getElapsedMs])

  const scheduleRotation = useCallback(() => {
    clearRotateTimer()
    rotateTimerRef.current = window.setTimeout(() => {
      const rec = recorderRef.current
      if (rec && rec.state === 'recording') {
        // Triggers ondataavailable (with a full, standalone container)
        // followed by onstop, which will start the next recorder.
        rec.stop()
      }
    }, CHUNK_INTERVAL_MS)
  }, [clearRotateTimer])

  const start = useCallback(async () => {
    if (recorderRef.current || streamRef.current) return
    if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
      throw new Error('Браузер не поддерживает запись аудио')
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
      },
    })
    streamRef.current = stream
    mimeTypeRef.current = pickMimeType()

    // analyser for VU
    const AudioCtxClass: typeof AudioContext =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext
    const ctx = new AudioCtxClass()
    audioCtxRef.current = ctx
    const source = ctx.createMediaStreamSource(stream)
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 1024
    source.connect(analyser)
    analyserRef.current = analyser

    accumulatedRef.current = 0
    chunkStartRef.current = 0
    recStartRef.current = performance.now()
    pauseAnchorRef.current = null

    shouldRotateRef.current = true
    startRecorder()
    scheduleRotation()

    setRecorderStatus('recording')
    startMeter()
  }, [scheduleRotation, setRecorderStatus, startMeter, startRecorder])

  const pause = useCallback(() => {
    const rec = recorderRef.current
    if (!rec) return
    shouldRotateRef.current = false
    clearRotateTimer()
    // Flush the in-flight chunk; new recorder won't be created because
    // shouldRotateRef is false.
    try {
      if (rec.state === 'recording') rec.stop()
    } catch {
      /* ignore */
    }
    // Capture elapsed so getElapsedMs continues correctly after resume.
    accumulatedRef.current += performance.now() - recStartRef.current
    pauseAnchorRef.current = performance.now()
    setRecorderStatus('paused')
    stopMeter()
  }, [clearRotateTimer, setRecorderStatus, stopMeter])

  const resume = useCallback(() => {
    if (!streamRef.current || pauseAnchorRef.current == null) return
    recStartRef.current = performance.now()
    pauseAnchorRef.current = null
    shouldRotateRef.current = true
    startRecorder()
    scheduleRotation()
    setRecorderStatus('recording')
    startMeter()
  }, [scheduleRotation, setRecorderStatus, startMeter, startRecorder])

  const stop = useCallback(async (): Promise<void> => {
    const rec = recorderRef.current
    shouldRotateRef.current = false
    clearRotateTimer()
    setRecorderStatus('stopping')
    if (rec && rec.state !== 'inactive') {
      await new Promise<void>((resolve) => {
        const onStop = () => {
          rec.removeEventListener('stop', onStop)
          resolve()
        }
        rec.addEventListener('stop', onStop)
        try {
          rec.stop()
        } catch {
          resolve()
        }
      })
    }
    cleanup()
    setRecorderStatus('idle')
  }, [cleanup, clearRotateTimer, setRecorderStatus])

  return { start, pause, resume, stop }
}
