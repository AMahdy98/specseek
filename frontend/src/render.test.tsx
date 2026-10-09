// Tests about *when* things render, not what they show.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { useElapsedSeconds } from './hooks'

// Count how often the citation list renders, by wrapping the real component.
const renders = vi.hoisted(() => ({ citations: 0 }))
vi.mock('./components/CitationList', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./components/CitationList')>()
  return {
    ...actual,
    CitationList: (props: Parameters<typeof actual.CitationList>[0]) => {
      renders.citations += 1
      return <actual.CitationList {...props} />
    },
  }
})

const ANSWER = {
  answer: 'It shall.',
  refused: false,
  strategy: 'section_aware',
  citations: [
    { document_id: 'd', document: 'Doc', clause_id: '1.1', heading: null, page: 1, snippet: 's', score: 0.9 },
  ],
}

describe('rendering', () => {
  it('typing a new question does not re-render the answer already on screen', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        Response.json(url.includes('/v1/documents') ? { items: [], next_cursor: null } : ANSWER),
      ),
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>,
    )
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Question'), 'What shall it do?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText('It shall.')
    const before = renders.citations

    await user.type(screen.getByLabelText('Question'), ' And twenty more characters')

    // The typed text is state of QuestionForm, so only the form re-renders.
    expect(renders.citations).toBe(before)
  })
})

describe('useElapsedSeconds', () => {
  it('counts whole seconds and stops its timer when the component goes away', () => {
    vi.useFakeTimers()
    const { result, unmount } = renderHook(() => useElapsedSeconds())
    expect(result.current).toBe(0)

    act(() => vi.advanceTimersByTime(3000))
    expect(result.current).toBe(3) // 1 would mean a stale closure

    unmount()
    expect(vi.getTimerCount()).toBe(0) // the cleanup ran: no interval left behind
  })
})
