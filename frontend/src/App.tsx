import { lazy, Suspense, useState } from 'react'

import type { AskParams } from './api'
import { AnswerSkeleton } from './components/AnswerSkeleton'
import { ErrorMessage } from './components/ErrorMessage'
import { QuestionForm } from './components/QuestionForm'
import { useAnswer, useDocuments } from './hooks'

// Lazy loading: the answer panel's code is a separate file the browser downloads only when
// it is first needed, not with the initial page. import() returns a promise for the module.
// Measured (docs/PERF.md): the panel is 0.7 kB gzipped, so this saves nothing here; it is
// kept as the pattern for when a heavy dependency (a markdown or PDF viewer) joins the panel.
const loadAnswerPanel = () => import('./components/AnswerPanel')
const AnswerPanel = lazy(() => loadAnswerPanel().then((m) => ({ default: m.AnswerPanel })))

export function App() {
  // The one piece of state that links form and answer: what was last submitted. The text
  // being typed stays inside the form, so typing does not re-render the answer.
  const [asked, setAsked] = useState<AskParams | null>(null)
  const documents = useDocuments()
  const answer = useAnswer(asked)

  function handleAsk(params: AskParams) {
    // Start fetching the panel's code now, in parallel with the question: by the time the
    // answer arrives (about a second) the code is already there.
    void loadAnswerPanel()
    setAsked(params)
  }

  return (
    <main>
      <h1>SpecSeek</h1>
      <p className="tagline">
        Answers from NASA and FDA software standards, with the clauses they come from.
      </p>
      <QuestionForm documents={documents.data} busy={answer.isFetching} onAsk={handleAsk} />
      {documents.isError && (
        <p className="notice">The document list could not be loaded; searching all documents.</p>
      )}
      {answer.isFetching && <AnswerSkeleton />}
      {!answer.isFetching && answer.isError && <ErrorMessage error={answer.error} />}
      {!answer.isFetching && answer.isSuccess && (
        // Suspense: what to show while a lazy component's code is still downloading.
        <Suspense fallback={<AnswerSkeleton />}>
          <AnswerPanel answer={answer.data} />
        </Suspense>
      )}
    </main>
  )
}
