import { useElapsedSeconds } from '../hooks'

// After this long the placeholder alone looks like a hang, so say what is happening.
// Typical answers take 1–2 s; a slow one means the server is retrying the provider.
const SHOW_COUNTER_AFTER_SECONDS = 3

/** Grey placeholder in the shape of an answer: the layout doesn't jump when the text arrives.
 *
 *  The seconds counter lives here, not in App: this component is the only thing that
 *  re-renders every second, and it only exists while a request is in flight. */
export function AnswerSkeleton() {
  const seconds = useElapsedSeconds()
  return (
    <section aria-label="Loading answer" aria-busy="true" className="skeleton">
      <div className="skeleton-line" />
      <div className="skeleton-line" />
      <div className="skeleton-line short" />
      {seconds >= SHOW_COUNTER_AFTER_SECONDS && (
        <p className="timings">Still working… {seconds} s</p>
      )}
    </section>
  )
}
