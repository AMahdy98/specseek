import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'
import './styles.css'

// One cache for the whole app, created once, outside any component (a component body runs
// on every render and would throw the cache away each time).
const queryClient = new QueryClient()

createRoot(document.getElementById('root') as HTMLElement).render(
  // StrictMode (development only): renders components twice and runs effects twice to
  // surface code that is not safe to repeat. It does not double network requests here:
  // TanStack Query deduplicates by query key.
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
