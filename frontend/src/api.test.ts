import { describe, expect, it, vi } from 'vitest'

import { ApiError, askQuestion, listDocuments, parseServerTiming } from './api'

function json(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
}

describe('parseServerTiming', () => {
  it('reads the three stages', () => {
    expect(parseServerTiming('embed;dur=283.5, search;dur=2, generate;dur=980')).toEqual({
      embed: 283.5,
      search: 2,
      generate: 980,
    })
  })

  it('returns nothing for a missing or malformed header', () => {
    expect(parseServerTiming(null)).toEqual({})
    expect(parseServerTiming('cache;desc="hit", bad;dur=abc')).toEqual({})
  })
})

describe('askQuestion', () => {
  it('posts the question and returns the answer with stage timings', async () => {
    const fetchMock = vi.fn(async () =>
      json(
        { answer: 'It shall.', refused: false, strategy: 'section_aware', citations: [] },
        { headers: { 'Server-Timing': 'embed;dur=300, search;dur=2, generate;dur=900' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const answer = await askQuestion({ question: 'What shall it do?', documentId: null })

    expect(answer.answer).toBe('It shall.')
    expect(answer.timingsMs).toEqual({ embed: 300, search: 2, generate: 900 })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://localhost:8000/v1/query')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ question: 'What shall it do?' })
  })

  it('sends document_id only when a document is selected', async () => {
    const fetchMock = vi.fn(async () =>
      json({ answer: 'x', refused: false, strategy: 'section_aware', citations: [] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await askQuestion({ question: 'What?', documentId: 'doc-1' })

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({ question: 'What?', document_id: 'doc-1' })
  })

  it('turns the API error envelope into an ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        json(
          { error: { code: 'provider_error', message: 'LLM unavailable', request_id: 'req-1' } },
          { status: 502 },
        ),
      ),
    )

    const error = await askQuestion({ question: 'What?', documentId: null }).catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 502, code: 'provider_error', requestId: 'req-1' })
  })

  it('copes with an error response that is not our JSON envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('<html>Bad Gateway</html>', { status: 502 })),
    )

    const error = await askQuestion({ question: 'What?', documentId: null }).catch((e) => e)

    expect(error).toMatchObject({ status: 502, code: 'http_error' })
  })

  it('reports a network failure when no response arrives', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )

    const error = await askQuestion({ question: 'What?', documentId: null }).catch((e) => e)

    expect(error).toMatchObject({ status: 0, code: 'network_error' })
  })

  it('passes a deliberate cancel through instead of reporting an error', async () => {
    const controller = new AbortController()
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            )
          }),
      ),
    )

    const pending = askQuestion({ question: 'What?', documentId: null }, controller.signal)
    controller.abort()
    const error = await pending.catch((e) => e)

    expect(error).not.toBeInstanceOf(ApiError)
    expect(error.name).toBe('AbortError')
  })
})

describe('listDocuments', () => {
  it('follows next_cursor until the last page', async () => {
    const doc = (id: string) => ({ id, title: id, chunk_count: 1, created_at: '2026-10-02T12:00:00Z' })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({ items: [doc('a')], next_cursor: 'c 1' }))
      .mockResolvedValueOnce(json({ items: [doc('b')], next_cursor: null }))
    vi.stubGlobal('fetch', fetchMock)

    const documents = await listDocuments()

    expect(documents.map((d) => d.id)).toEqual(['a', 'b'])
    expect(fetchMock.mock.calls[1]?.[0]).toBe('http://localhost:8000/v1/documents?limit=100&cursor=c%201')
  })
})
