import { ApiError } from '../api'

// What the user should do, by error code. The server's own message is for developers and
// logs; codes are the stable part of the contract (app/errors.py).
const ADVICE: Record<string, string> = {
  provider_error: 'The language model is unavailable right now. Try again in a minute.',
  timeout: 'The server took too long to answer. Try again.',
  network_error: 'Could not reach the server. Check that the API is running.',
  validation_error: 'The question was rejected. It must be between 3 and 1000 characters.',
  not_found: 'The selected document no longer exists. Pick another one.',
}

export function ErrorMessage({ error }: { error: Error }) {
  const apiError = error instanceof ApiError ? error : null
  const advice = (apiError && ADVICE[apiError.code]) ?? 'Something went wrong. Try again.'
  return (
    // role="alert": screen readers announce it as soon as it appears.
    <div role="alert" className="error">
      <p>{advice}</p>
      {apiError?.requestId && (
        <p className="error-meta">
          If this keeps happening, quote request ID <code>{apiError.requestId}</code>
        </p>
      )}
    </div>
  )
}
