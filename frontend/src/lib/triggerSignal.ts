import type { TodoTask, TriggerEvent } from './types'
import { dateTriggerLabel, isDateTriggerRef } from './triggerCatalog'

function extTriggerRef(task: TodoTask): string {
  const ext = task.extensions?.find((item) => item.extensionName === 'com.triggertodo.meta')
  return String(ext?.triggerRef || '').trim()
}

function dueReached(task: TodoTask): boolean {
  const value = task.dueDateTime?.dateTime
  if (!value) return false
  const at = new Date(value).getTime()
  if (Number.isNaN(at)) return false
  return at <= Date.now()
}

export function triggerDisplay(task: TodoTask, eventsById?: Map<number, TriggerEvent>): string {
  const ref = extTriggerRef(task)
  if (isDateTriggerRef(ref)) return dateTriggerLabel(ref)
  if (ref.startsWith('event:')) {
    const id = Number(ref.slice('event:'.length))
    const eventName = Number.isFinite(id) ? eventsById?.get(id)?.name : ''
    return eventName ? `event: ${eventName}` : `event: #${ref.slice('event:'.length)}`
  }
  if (ref) return `rule #${ref}`
  if (task.dueDateTime?.dateTime) return 'date trigger'
  if (task.recurrence?.pattern) return 'recurrence trigger'
  return 'none'
}

export function isTaskTriggered(task: TodoTask, eventsById?: Map<number, TriggerEvent>): boolean {
  const ref = extTriggerRef(task)
  if (isDateTriggerRef(ref)) return dueReached(task)

  if (ref.startsWith('event:')) {
    const id = Number(ref.slice('event:'.length))
    if (!Number.isFinite(id)) return false
    return Boolean(eventsById?.get(id)?.is_active)
  }

  if (ref) return true
  return Boolean(task.dueDateTime?.dateTime || task.recurrence?.pattern)
}

export function hasAnyTriggerConfigured(task: TodoTask): boolean {
  const ref = extTriggerRef(task)
  return Boolean(ref || task.dueDateTime?.dateTime || task.recurrence?.pattern)
}
