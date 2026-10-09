import { useState } from 'react'

import type { AskParams } from './api'
import { AnswerPanel, AnswerSkeleton } from './components/AnswerPanel'
import { ErrorMessage } from './components/ErrorMessage'
import { QuestionForm } from './components/QuestionForm'
import { useAnswer, useDocuments } from './hooks'

export function App() {
  // The one piece of state that links form and answer: what was last submitted. The text
  // being typed stays inside the form, so typing does not re-render the answer.
  const [asked, setAsked] = useState<AskParams | null>(null)
  const documents = useDocuments()
  const answer = useAnswer(asked)

  return (
    <main>
      <h1>SpecSeek</h1>
      <p className="tagline">
        Answers from NASA and FDA software standards, with the clauses they come from.
      </p>
      <QuestionForm documents={documents.data} busy={answer.isFetching} onAsk={setAsked} />
      {documents.isError && (
        <p className="notice">The document list could not be loaded; searching all documents.</p>
      )}
      {answer.isFetching && <AnswerSkeleton />}
      {!answer.isFetching && answer.isError && <ErrorMessage error={answer.error} />}
      {!answer.isFetching && answer.isSuccess && <AnswerPanel answer={answer.data} />}
    </main>
  )
}
