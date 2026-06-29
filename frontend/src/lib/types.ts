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

export interface TriggerMilestoneEpic {
  epic_key: string
  name: string
  status?: string | null
  priority?: string | null
}

export interface TriggerMilestoneTask {
  task_id: string
  list_id?: string | null
  title: string
  status?: string | null
  due_datetime?: string | null
}

export interface TriggerMilestoneScrum {
  id: number
  name: string
  status?: string | null
  start_date?: string | null
  end_date?: string | null
}

export interface TriggerMilestone {
  id: number
  title: string
  milestone_at?: string | null
  location?: string | null
  notes?: string | null
  updated_at: string
  epic_keys: string[]
  task_ids: string[]
  scrum_ids: string[]
  summary: {
    epics: number
    tasks: number
    scrums: number
  }
  epics: TriggerMilestoneEpic[]
  tasks: TriggerMilestoneTask[]
  scrums: TriggerMilestoneScrum[]
}

export interface TriggerScrumTask {
  list_id: string
  task_id: string
  title: string
  status?: string | null
  wf_status?: string | null
  importance?: string | null
  due_datetime?: string | null
  trigger_ref?: string | null
  epic_key?: string | null
  source?: TaskSource | null
}

export interface TriggerScrumItem {
  id: number
  list_id: string
  task_id: string
  points: number
  status: 'todo' | 'doing' | 'done'
  added_after_start: boolean
  updated_at: string
  task?: TriggerScrumTask | null
}

export interface TriggerScrum {
  id: number
  name: string
  goal?: string | null
  start_date?: string | null
  end_date?: string | null
  target_points: number
  status: 'draft' | 'active' | 'completed'
  completed_at?: string | null
  updated_at: string
  summary: {
    items: number
    points: number
    done_points: number
    points_by_status: Record<'todo' | 'doing' | 'done', number>
    count_by_status: Record<'todo' | 'doing' | 'done', number>
    added_after_start: number
  }
  items: TriggerScrumItem[]
}

export interface TriggerRoutineCheck {
  id: number
  list_id: string
  task_id: string
  check_date: string
  updated_at: string
}
