import { useState, type FormEvent } from 'react'

import type { AskParams, DocumentSummary } from '../api'

// Same limits as QueryRequest in app/models.py. The server still validates: this only saves
// the user a round trip.
const MIN_LENGTH = 3
const MAX_LENGTH = 1000

interface Props {
  documents: DocumentSummary[] | undefined // undefined while loading or if the list failed
  busy: boolean
  onAsk: (params: AskParams) => void
}

export function QuestionForm({ documents, busy, onAsk }: Props) {
  // Client state: exists only in this browser tab, the server never hears of it until submit.
  const [question, setQuestion] = useState('')
  const [documentId, setDocumentId] = useState('') // '' = all documents

  const trimmed = question.trim()
  const canSubmit = trimmed.length >= MIN_LENGTH && !busy

  function handleSubmit(event: FormEvent) {
    event.preventDefault() // the browser's default is a full page reload
    if (canSubmit) onAsk({ question: trimmed, documentId: documentId || null })
  }

  return (
    <form className="question-form" onSubmit={handleSubmit}>
      <label htmlFor="question">Question</label>
      <textarea
        id="question"
        rows={3}
        maxLength={MAX_LENGTH}
        placeholder="e.g. What makes a piece of software count as safety-critical?"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
      />
      <div className="form-row">
        <label htmlFor="document">Search in</label>
        <select
          id="document"
          value={documentId}
          onChange={(event) => setDocumentId(event.target.value)}
        >
          <option value="">All documents</option>
          {documents?.map((doc) => (
            // key: a stable identity per row, so React can match old and new list items.
            <option key={doc.id} value={doc.id}>
              {doc.title}
            </option>
          ))}
        </select>
        <button type="submit" disabled={!canSubmit}>
          {busy ? 'Searching…' : 'Ask'}
        </button>
      </div>
    </form>
  )
}
