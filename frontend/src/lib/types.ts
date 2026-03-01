export type Importance = 'low' | 'normal' | 'high'
export type TaskSource = 'microsoft-todo' | 'jira' | 'triggertodo'

export interface TodoList {
  id: string
  displayName: string
}

export interface RecurrencePayload {
  pattern: Record<string, unknown>
  range: Record<string, unknown>
}

export interface TaskExtensions {
  pool?: string | null
  wfStatus?: string | null
  triggerRef?: string | null
  epicKey?: string | null
  source?: TaskSource | null
}

export interface TodoTask {
  id: string
  title: string
  source: TaskSource
  status?: string
  importance?: string
  createdDateTime?: string | null
  lastModifiedDateTime?: string | null
  body?: {
    contentType?: string
    content?: string
  }
  dueDateTime?: {
    dateTime: string
    timeZone: string
  } | null
  recurrence?: RecurrencePayload | null
  extensions?: Array<
    TaskExtensions & {
      id?: string
      extensionName?: string
    }
  >
  listId: string
}

export interface TriggerRule {
  id: number
  name: string
  source_pool?: string | null
  source_wf_status?: string | null
  target_pool?: string | null
  target_wf_status?: string | null
  enabled: boolean
  cron_expression?: string | null
  updated_at: string
}

export interface TriggerMonitor {
  matchingTasks: number
  selectedTasks: number
  dueSignals: number
  recurrenceSignals: number
  lastSignalAt?: string | null
}

export interface TriggerRuleWithMonitor extends TriggerRule {
  monitor: TriggerMonitor
}

export interface TriggerEvent {
  id: number
  name: string
  is_active: boolean
  occurred_at?: string | null
  updated_at: string
}
