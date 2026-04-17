import { useEffect, useRef, useState } from 'react'

import type { Speaker, Transcript } from '../api/sessions'
import {
  SPEAKER_BADGE,
  SPEAKER_LABEL,
  formatChunkTimestamp,
} from '../lib/formatters'

interface Props {
  transcript: Transcript
  onEdit: (id: string, patch: { text?: string; speaker?: Speaker }) => void
  onDelete: (id: string) => void
  busy?: boolean
}

export function TranscriptItem({ transcript, onEdit, onDelete, busy }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(transcript.text)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    setDraft(transcript.text)
  }, [transcript.text])

  useEffect(() => {
    if (editing && textareaRef.current) {
      textareaRef.current.focus()
      textareaRef.current.select()
    }
  }, [editing])

  const lowConfidence =
    transcript.confidence !== null && transcript.confidence < 0.6

  const save = () => {
    const trimmed = draft.trim()
    if (trimmed.length === 0) {
      setDraft(transcript.text)
      setEditing(false)
      return
    }
    if (trimmed === transcript.text) {
      setEditing(false)
      return
    }
    onEdit(transcript.id, { text: trimmed })
    setEditing(false)
  }

  const handleDelete = () => {
    if (window.confirm('Удалить реплику?')) {
      onDelete(transcript.id)
    }
  }

  const handleSpeakerChange = (speaker: Speaker) => {
    if (speaker === transcript.speaker) return
    onEdit(transcript.id, { speaker })
  }

  return (
    <li
      className={`border rounded-xl p-3 bg-white flex flex-col gap-2 ${
        lowConfidence ? 'border-amber-300 bg-amber-50/50' : 'border-slate-200'
      }`}
    >
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <span
          className={`inline-flex items-center rounded-full border px-2 py-0.5 font-medium ${SPEAKER_BADGE[transcript.speaker]}`}
        >
          {SPEAKER_LABEL[transcript.speaker]}
        </span>
        <span>
          {formatChunkTimestamp(transcript.started_at_ms)} –{' '}
          {formatChunkTimestamp(transcript.ended_at_ms)}
        </span>
        {transcript.edited_by_user && (
          <span className="text-slate-400">· отредактировано</span>
        )}
        {lowConfidence && (
          <span className="text-amber-700">· низкая уверенность</span>
        )}
      </div>

      {editing ? (
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              save()
            } else if (e.key === 'Escape') {
              setDraft(transcript.text)
              setEditing(false)
            }
          }}
          rows={Math.max(2, Math.min(8, draft.split('\n').length + 1))}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-300 text-sm"
          disabled={busy}
        />
      ) : (
        <p
          className="text-slate-800 text-sm whitespace-pre-wrap cursor-text"
          onDoubleClick={() => !busy && setEditing(true)}
          title="Двойной клик для редактирования"
        >
          {transcript.text || (
            <span className="text-slate-400 italic">(пусто)</span>
          )}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {editing ? (
          <>
            <button
              type="button"
              onClick={save}
              disabled={busy}
              className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100"
            >
              Сохранить
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(transcript.text)
                setEditing(false)
              }}
              className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-100"
            >
              Отмена
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            disabled={busy}
            className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-100"
          >
            Редактировать
          </button>
        )}

        <label className="flex items-center gap-1">
          <span className="text-slate-500">Говорящий:</span>
          <select
            value={transcript.speaker}
            onChange={(e) => handleSpeakerChange(e.target.value as Speaker)}
            disabled={busy}
            className="rounded border border-slate-200 bg-white px-1.5 py-1"
          >
            <option value="doctor">Врач</option>
            <option value="patient">Пациент</option>
            <option value="unknown">Неизвестно</option>
          </select>
        </label>

        <button
          type="button"
          onClick={handleDelete}
          disabled={busy}
          className="ml-auto rounded border border-red-200 text-red-700 px-2 py-1 hover:bg-red-50"
        >
          Удалить
        </button>
      </div>
    </li>
  )
}
