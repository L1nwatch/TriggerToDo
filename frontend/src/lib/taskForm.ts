import type { TodoTask } from './types'

export interface TaskFormModel {
  title: string
  listId: string
  notes: string
  dueAt: string
  wfStatus: string
  triggerRef: string
  epicKey: string
  recurrenceType: 'none' | 'daily' | 'weekly' | 'monthly' | 'yearly'
  recurrenceInterval: number
}

export function defaultTaskForm(listId = ''): TaskFormModel {
  return {
    title: '',
    listId,
    notes: '',
    dueAt: '',
    wfStatus: 'todo',
    triggerRef: '',
    epicKey: '',
    recurrenceType: 'none',
    recurrenceInterval: 1,
  }
}

function toLocalDateTimeInputValue(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

function localDateInputValue(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function userTimeZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}

function getExtension(task: TodoTask, field: 'wfStatus' | 'triggerRef' | 'epicKey') {
  const ext = (task.extensions || []).find((item) => item.extensionName === 'com.triggertodo.meta')
  return ext?.[field] || ''
}

export function formFromTask(task: TodoTask): TaskFormModel {
  const model = defaultTaskForm(task.listId)
  model.title = task.title
  model.notes = task.body?.content || ''
  model.wfStatus = getExtension(task, 'wfStatus')
  model.triggerRef = getExtension(task, 'triggerRef')
  model.epicKey = getExtension(task, 'epicKey')
  if (!model.triggerRef && task.dueDateTime?.dateTime) {
    model.triggerRef = 'date'
  }

  if (task.dueDateTime?.dateTime) {
    model.dueAt = toLocalDateTimeInputValue(task.dueDateTime.dateTime)
  }

  const recurrenceType = String(task.recurrence?.pattern?.['type'] || '').toLowerCase()
  if (recurrenceType === 'daily' || recurrenceType === 'weekly' || recurrenceType === 'monthly' || recurrenceType === 'yearly') {
    model.recurrenceType = recurrenceType
    const rawInterval = Number(task.recurrence?.pattern?.['interval'])
    if (Number.isFinite(rawInterval) && rawInterval > 0) model.recurrenceInterval = rawInterval
  }

  return model
}

export function taskPayloadFromForm(model: TaskFormModel, options?: { includeSource?: boolean }) {
  const payload: Record<string, unknown> = {
    title: model.title,
    body: {
      contentType: 'text',
      content: model.notes,
    },
    extensions: {
      wfStatus: model.wfStatus || null,
      triggerRef: model.triggerRef || null,
      epicKey: model.epicKey || null,
      source: options?.includeSource ? 'triggertodo' : null,
    },
  }

  if (model.dueAt) {
    payload.dueDateTime = {
      dateTime: new Date(model.dueAt).toISOString(),
      timeZone: userTimeZone(),
    }
  } else {
    payload.dueDateTime = null
  }

  if (model.recurrenceType !== 'none') {
    const today = localDateInputValue()
    payload.recurrence = {
      pattern: {
        type: model.recurrenceType,
        interval: model.recurrenceInterval,
      },
      range: {
        type: 'noEnd',
        startDate: today,
      },
    }
  } else {
    payload.recurrence = null
  }

  return payload
}
