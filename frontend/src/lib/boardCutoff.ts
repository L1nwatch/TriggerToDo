import type { TodoTask } from './types'

export const BOARD_CUTOFF_ISO = '2026-01-01T00:00:00Z'
const BOARD_CUTOFF_MS = Date.parse(BOARD_CUTOFF_ISO)

function toMs(value?: string | null): number | null {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isFinite(ms) ? ms : null
}

export function isOnOrAfterBoardCutoff(task: TodoTask): boolean {
  const createdMs = toMs(task.createdDateTime)
  const modifiedMs = toMs(task.lastModifiedDateTime)
  if (createdMs !== null && createdMs >= BOARD_CUTOFF_MS) return true
  if (modifiedMs !== null && modifiedMs >= BOARD_CUTOFF_MS) return true
  return false
}

