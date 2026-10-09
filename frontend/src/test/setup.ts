// Runs before every test file.
import '@testing-library/jest-dom/vitest' // adds matchers such as toBeInTheDocument()
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup() // unmount what the test rendered
  vi.unstubAllGlobals() // put the real fetch back
  vi.useRealTimers() // in case a test replaced the clock
})
