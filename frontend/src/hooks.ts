// Server state: everything here is a copy of data the server owns. TanStack Query keeps the
// copies, their loading/error status, and decides when a copy is too old to trust.

import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { ApiError, askQuestion, listDocuments, type AskParams } from './api'

/** Retry only when no response arrived at all, and only once.
 *  A 4xx will fail the same way again; a 502 means the server already retried the provider
 *  3 times, and each client retry would spend 3 more generations of a 500/day quota. */
export function shouldRetry(failureCount: number, error: Error): boolean {
  return error instanceof ApiError && error.code === 'network_error' && failureCount < 1
}

/** Whole seconds since the calling component appeared on screen.
 *
 *  useEffect is for syncing with something outside React; here, a browser timer. The effect
 *  runs after the component is on screen; the function it returns is the cleanup, run when
 *  the component leaves. Without the cleanup the interval would tick forever (a leak, like
 *  a thread nobody joins). */
export function useElapsedSeconds(): number {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    // The updater form `s => s + 1` asks React for the latest value. `setSeconds(seconds + 1)`
    // would be the classic stale closure: this callback is created once and would forever
    // see the `seconds` of that first render (0), so the counter would stick at 1.
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, []) // []: run once after mount, clean up at unmount
  return seconds
}

export function useDocuments() {
  return useQuery({
    queryKey: ['documents'],
    queryFn: ({ signal }) => listDocuments(signal),
    staleTime: 60_000, // the list changes only on ingest; don't refetch on every focus
    retry: shouldRetry,
  })
}

/** The answer to the submitted question; idle while `params` is null.
 *
 *  A POST, but semantically a read, so it is a query and not a mutation: the same question
 *  about the same documents gives the same answer (temperature 0), which makes it cacheable.
 *  The key is the cache identity: asking a question again is served from memory. */
export function useAnswer(params: AskParams | null) {
  return useQuery({
    queryKey: ['answer', params?.question, params?.documentId],
    // `signal` is aborted when this query is no longer needed: the in-flight request is cancelled.
    queryFn: ({ signal }) => askQuestion(params as AskParams, signal),
    enabled: params !== null,
    staleTime: Infinity, // never refetch behind the user's back: every call costs quota
    gcTime: 30 * 60_000, // keep unused answers for 30 minutes, then free the memory
    retry: shouldRetry,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}
