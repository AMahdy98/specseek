// The only file that talks HTTP. Types mirror app/models.py; if the API changes shape,
// this is where the compiler starts complaining.

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

// The server retries the LLM up to 3 times with waits, so a slow answer is not yet a failure.
const TIMEOUT_MS = 60_000

export type Strategy = 'naive' | 'section_aware'

export interface Citation {
  document_id: string
  document: string
  clause_id: string | null
  heading: string | null
  page: number
  snippet: string
  score: number
}

export interface QueryResponse {
  answer: string
  refused: boolean
  strategy: Strategy
  citations: Citation[]
}

export interface Answer extends QueryResponse {
  timingsMs: Record<string, number> // from the Server-Timing header; empty if absent
}

export interface DocumentSummary {
  id: string
  title: string
  chunk_count: number
  created_at: string
}

export interface DocumentPage {
  items: DocumentSummary[]
  next_cursor: string | null
}

export interface AskParams {
  question: string
  documentId: string | null
}

/** Every failure the UI can show: an API error envelope, a network failure, or a timeout. */
export class ApiError extends Error {
  readonly status: number // 0 when no HTTP response arrived
  readonly code: string
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

/** "embed;dur=283, search;dur=2" → { embed: 283, search: 2 } */
export function parseServerTiming(header: string | null): Record<string, number> {
  const timings: Record<string, number> = {}
  for (const entry of (header ?? '').split(',')) {
    const [name, ...params] = entry.trim().split(';')
    const dur = params.map((p) => p.trim()).find((p) => p.startsWith('dur='))
    const value = dur === undefined ? NaN : Number(dur.slice(4))
    if (name && Number.isFinite(value)) timings[name] = value
  }
  return timings
}

async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get('X-Request-ID')
  try {
    const body = await response.json()
    const error = body?.error
    if (typeof error?.code === 'string' && typeof error?.message === 'string') {
      return new ApiError(response.status, error.code, error.message, error.request_id ?? requestId)
    }
  } catch {
    // Not JSON (e.g. an HTML error page from a proxy): fall through to the generic error.
  }
  return new ApiError(response.status, 'http_error', `Request failed (HTTP ${response.status}).`, requestId)
}

async function request(path: string, init: RequestInit, signal?: AbortSignal): Promise<Response> {
  // One controller, two triggers: our timeout, and the caller's signal (TanStack Query aborts
  // it when the component unmounts or the question changes).
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, TIMEOUT_MS)
  const onCallerAbort = () => controller.abort()
  if (signal?.aborted) controller.abort()
  signal?.addEventListener('abort', onCallerAbort)

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal })
  } catch (cause) {
    if (timedOut) {
      throw new ApiError(0, 'timeout', 'The server took too long to answer.', null)
    }
    if (signal?.aborted) throw cause // a deliberate cancel, not an error to show
    // fetch rejects only when no response arrived: server down, DNS, or blocked by CORS.
    throw new ApiError(0, 'network_error', 'Could not reach the server.', null)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onCallerAbort)
  }
  // fetch does NOT reject on 4xx/5xx; a 502 is a successful HTTP exchange. We must check.
  if (!response.ok) throw await toApiError(response)
  return response
}

export async function listDocuments(signal?: AbortSignal): Promise<DocumentSummary[]> {
  // Follows next_cursor to the end: the list feeds a dropdown and the corpus is a few documents.
  const documents: DocumentSummary[] = []
  let cursor: string | null = null
  do {
    const query: string = cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`
    const response = await request(`/v1/documents?limit=100${query}`, {}, signal)
    const page = (await response.json()) as DocumentPage
    documents.push(...page.items)
    cursor = page.next_cursor
  } while (cursor !== null)
  return documents
}

export async function askQuestion(params: AskParams, signal?: AbortSignal): Promise<Answer> {
  const response = await request(
    '/v1/query',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: params.question,
        ...(params.documentId === null ? {} : { document_id: params.documentId }),
      }),
    },
    signal,
  )
  const body = (await response.json()) as QueryResponse
  return { ...body, timingsMs: parseServerTiming(response.headers.get('Server-Timing')) }
}
