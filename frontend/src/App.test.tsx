import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { ApiError } from './api'
import { headingLabel } from './components/CitationList'
import { shouldRetry } from './hooks'

const DOCUMENTS = {
  items: [{ id: 'doc-1', title: 'NPR 7150.2D', chunk_count: 695, created_at: '2026-10-03T11:27:00Z' }],
  next_cursor: null,
}

const ANSWER = {
  answer: 'The project manager shall maintain a software development plan (3.1.3).',
  refused: false,
  strategy: 'section_aware',
  citations: [
    {
      document_id: 'doc-1',
      document: 'NPR 7150.2D',
      clause_id: '3.1.3',
      heading: 'Software Life Cycle Planning',
      page: 21,
      snippet: 'The project manager shall develop, maintain, and execute software plans',
      score: 0.8123,
    },
  ],
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Fake server: answers GET /v1/documents itself, hands POST /v1/query to the test. */
function stubApi(onQuery: (body: Record<string, unknown>) => Response) {
  const queries: Record<string, unknown>[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes('/v1/documents')) return json(DOCUMENTS)
      const body = JSON.parse(init?.body as string)
      queries.push(body)
      return onQuery(body)
    }),
  )
  return queries
}

function renderApp() {
  // A fresh cache per test, or one test's answer would be served to the next.
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

async function ask(user: ReturnType<typeof userEvent.setup>, question: string) {
  await user.clear(screen.getByLabelText('Question'))
  await user.type(screen.getByLabelText('Question'), question)
  await user.click(screen.getByRole('button', { name: 'Ask' }))
}

describe('App', () => {
  it('shows the answer and its sources', async () => {
    const queries = stubApi(() => json(ANSWER))
    const user = renderApp()

    await ask(user, 'Who maintains the software plan?')

    expect(await screen.findByText(ANSWER.answer)).toBeInTheDocument()
    expect(screen.getByText('Sources given to the model')).toBeInTheDocument()
    expect(screen.getByText('3.1.3')).toBeInTheDocument()
    expect(screen.getByText(/page 21 · similarity 0\.81/)).toBeInTheDocument()
    expect(queries).toEqual([{ question: 'Who maintains the software plan?' }])
  })

  it('restricts the search to the selected document', async () => {
    const queries = stubApi(() => json(ANSWER))
    const user = renderApp()

    await user.selectOptions(
      screen.getByLabelText('Search in'),
      await screen.findByRole('option', { name: 'NPR 7150.2D' }),
    )
    await ask(user, 'Who maintains the software plan?')
    await screen.findByText(ANSWER.answer)

    expect(queries[0]).toMatchObject({ document_id: 'doc-1' })
  })

  it('keeps the Ask button disabled until the question has 3 characters', async () => {
    stubApi(() => json(ANSWER))
    const user = renderApp()
    const button = screen.getByRole('button', { name: 'Ask' })

    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Question'), '  ab  ')
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Question'), 'c')
    expect(button).toBeEnabled()
  })

  it('marks a refusal as "not in the documents", not as an answer with sources', async () => {
    stubApi(() =>
      json({ ...ANSWER, answer: "I don't know based on these documents.", refused: true }),
    )
    const user = renderApp()

    await ask(user, 'What is the capital of France?')

    expect(await screen.findByText(/don't contain an answer/)).toBeInTheDocument()
    expect(screen.getByText('Passages searched')).toBeInTheDocument()
    expect(screen.queryByText('Sources given to the model')).not.toBeInTheDocument()
  })

  it('shows advice and the request ID when the LLM provider fails, without retrying', async () => {
    const queries = stubApi(() =>
      json(
        { error: { code: 'provider_error', message: 'LLM provider unavailable', request_id: 'req-42' } },
        502,
      ),
    )
    const user = renderApp()

    await ask(user, 'Who maintains the software plan?')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The language model is unavailable right now')
    expect(alert).toHaveTextContent('req-42')
    expect(alert).not.toHaveTextContent('LLM provider unavailable') // the raw message stays out
    expect(queries).toHaveLength(1)
  })

  it('renders HTML in the model output as plain text', async () => {
    const hostile = 'See <img src=x onerror="window.pwned = true"> and <b>bold</b>.'
    stubApi(() => json({ ...ANSWER, answer: hostile }))
    const user = renderApp()

    await ask(user, 'Who maintains the software plan?')

    const answer = await screen.findByText(hostile) // the characters themselves are on screen
    expect(answer.querySelector('img, b')).toBeNull() // and no element was created from them
  })

  it('answers a repeated question from the cache, without a second request', async () => {
    const queries = stubApi((body) => json({ ...ANSWER, answer: `Answer to: ${body.question}` }))
    const user = renderApp()

    await ask(user, 'First question?')
    await screen.findByText('Answer to: First question?')
    await ask(user, 'Second question?')
    await screen.findByText('Answer to: Second question?')
    await ask(user, 'First question?')
    await screen.findByText('Answer to: First question?')

    expect(queries.map((q) => q.question)).toEqual(['First question?', 'Second question?'])
  })
})

describe('headingLabel', () => {
  it('does not repeat the clause number, and marks a parent section as such', () => {
    expect(headingLabel({ clause_id: '4.2', heading: '4.2 Safety-Critical Software' })).toBe(
      'Safety-Critical Software',
    )
    expect(headingLabel({ clause_id: '3.7.3', heading: '3.7 Safety-Critical Software' })).toBe(
      '(in 3.7 Safety-Critical Software)',
    )
    expect(headingLabel({ clause_id: null, heading: 'Preface' })).toBe('Preface')
    expect(headingLabel({ clause_id: '4.2', heading: null })).toBe('')
  })
})

describe('shouldRetry', () => {
  it('retries a network failure once, and nothing else', () => {
    const network = new ApiError(0, 'network_error', 'x', null)
    expect(shouldRetry(0, network)).toBe(true)
    expect(shouldRetry(1, network)).toBe(false)
    expect(shouldRetry(0, new ApiError(502, 'provider_error', 'x', null))).toBe(false)
    expect(shouldRetry(0, new ApiError(422, 'validation_error', 'x', null))).toBe(false)
    expect(shouldRetry(0, new ApiError(0, 'timeout', 'x', null))).toBe(false)
  })
})
