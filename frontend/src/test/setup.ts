import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

export {}

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean | undefined
}

// @testing-library/react needs React's act() environment flag under jsdom.
globalThis.IS_REACT_ACT_ENVIRONMENT = true

// Auto-cleanup only registers itself when vitest globals are on; we run with
// explicit imports, so detach the DOM after each test here.
afterEach(cleanup)
