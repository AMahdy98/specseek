import type { Answer } from '../api'
import { CitationList } from './CitationList'

const STAGES = ['embed', 'search', 'generate']

export function AnswerPanel({ answer }: { answer: Answer }) {
  const timings = STAGES.filter((stage) => stage in answer.timingsMs)
    .map((stage) => `${stage} ${Math.round(answer.timingsMs[stage] ?? 0)} ms`)
    .join(' · ')

  return (
    <section aria-label="Answer">
      {answer.refused && (
        <p className="notice">
          The documents don&apos;t contain an answer to this question. The passages below are the
          closest matches that were searched.
        </p>
      )}
      {/* The answer is LLM output, i.e. untrusted text. Rendered as a text node, React escapes
          it: "<script>" shows up as those characters. Never dangerouslySetInnerHTML here. */}
      <p className="answer">{answer.answer}</p>
      {timings && <p className="timings">{timings}</p>}
      <CitationList citations={answer.citations} refused={answer.refused} />
    </section>
  )
}

/** Grey placeholder in the shape of an answer: the layout doesn't jump when the text arrives. */
export function AnswerSkeleton() {
  return (
    <section aria-label="Loading answer" aria-busy="true" className="skeleton">
      <div className="skeleton-line" />
      <div className="skeleton-line" />
      <div className="skeleton-line short" />
    </section>
  )
}
