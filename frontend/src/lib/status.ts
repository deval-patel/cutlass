/** Shared status helpers. */

import type { JobStatusValue } from '../types'

export const TERMINAL: JobStatusValue[] = ['ready', 'rendered', 'failed']
export const SHOWABLE: JobStatusValue[] = ['ready', 'rendered', 'rendering']

export function isTerminal(status: JobStatusValue): boolean {
  return TERMINAL.includes(status)
}

export function fmtSeconds(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}
