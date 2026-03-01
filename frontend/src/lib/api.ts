import type { TodoList, TodoTask, TriggerEvent, TriggerRule, TriggerRuleWithMonitor } from './types'
import { isOnOrAfterBoardCutoff } from './boardCutoff'

const JSON_HEADERS = {
  'Content-Type': 'application/json',
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function request<T>(path: string, init: RequestInit = {}, attempt = 0): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init.body ? JSON_HEADERS : {}),
      ...(init.headers || {}),
    },
  })

  if (!response.ok) {
    if ((response.status === 429 || response.status === 503) && attempt < 4) {
      const retryAfter = Number(response.headers.get('Retry-After') || '0')
      const delayMs = Math.max(800, (Number.isFinite(retryAfter) ? retryAfter : 0) * 1000) * (attempt + 1)
      await sleep(delayMs)
      return request<T>(path, init, attempt + 1)
    }

    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

function asCollection<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (payload && typeof payload === 'object' && Array.isArray((payload as { value?: unknown }).value)) {
    return (payload as { value: T[] }).value
  }
  return []
}

export async function getCurrentUser() {
  return request<{ session: { name?: string; email?: string } }>('/api/auth/me')
}

export async function logout() {
  return request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' })
}

export async function listTodoLists() {
  const payload = await request<unknown>('/api/todo/lists')
  return asCollection<TodoList>(payload)
}

export async function createList(displayName: string) {
  return request<TodoList>('/api/todo/lists', {
    method: 'POST',
    body: JSON.stringify({ displayName }),
  })
}

export async function listTasks(listId: string) {
  const payload = await request<unknown>(`/api/todo/lists/${listId}/tasks`)
  const tasks = asCollection<Omit<TodoTask, 'listId' | 'source'>>(payload)
  return tasks.map((task) => ({ ...task, listId, source: 'microsoft-todo' as const }))
}

export async function fetchAllTasks() {
  const lists = await listTodoLists()
  const cache = await queryCachedTasks()
  const tasksByList: TodoTask[][] = [
    cache.items.map((item) => ({
      id: item.taskId,
      listId: item.listId,
      source: item.source || 'microsoft-todo',
      title: item.title,
      status: item.status,
      importance: item.importance as TodoTask['importance'],
      createdDateTime: item.createdDateTime || null,
      lastModifiedDateTime: item.lastModifiedDateTime || null,
      body: { contentType: 'text', content: item.bodyContent || '' },
      dueDateTime: item.dueDateTime
        ? { dateTime: item.dueDateTime, timeZone: item.dueTimeZone || 'UTC' }
        : null,
      recurrence: item.recurrenceJson
        ? (JSON.parse(item.recurrenceJson) as { pattern: Record<string, unknown>; range: Record<string, unknown> })
        : null,
      extensions: [
        {
          extensionName: 'com.triggertodo.meta',
          pool: item.pool || null,
          wfStatus: item.wfStatus || null,
          triggerRef: item.triggerRef || null,
          epicKey: item.epicKey || null,
          source: item.source || 'microsoft-todo',
        },
      ],
    })),
  ]
  const allTasks = tasksByList.flat()
  return {
    lists,
    tasks: allTasks.filter((task) => isOnOrAfterBoardCutoff(task)),
  }
}

export async function getTask(listId: string, taskId: string) {
  const cache = await queryCachedTasks()
  const item = cache.items.find((row) => row.listId === listId && row.taskId === taskId)
  if (item) {
    return {
      id: item.taskId,
      listId: item.listId,
      source: item.source || 'microsoft-todo',
      title: item.title,
      status: item.status,
      importance: item.importance as TodoTask['importance'],
      createdDateTime: item.createdDateTime || null,
      lastModifiedDateTime: item.lastModifiedDateTime || null,
      body: { contentType: 'text', content: item.bodyContent || '' },
      dueDateTime: item.dueDateTime
        ? { dateTime: item.dueDateTime, timeZone: item.dueTimeZone || 'UTC' }
        : null,
      recurrence: item.recurrenceJson
        ? (JSON.parse(item.recurrenceJson) as { pattern: Record<string, unknown>; range: Record<string, unknown> })
        : null,
      extensions: [
        {
          extensionName: 'com.triggertodo.meta',
          pool: item.pool || null,
          wfStatus: item.wfStatus || null,
          triggerRef: item.triggerRef || null,
          epicKey: item.epicKey || null,
          source: item.source || 'microsoft-todo',
        },
      ],
    }
  }
  const tasks = await listTasks(listId)
  return tasks.find((task) => task.id === taskId) || null
}

export async function createTask(
  listId: string,
  payload: {
    title: string
    body?: { contentType: 'text'; content: string }
    importance?: string
    dueDateTime?: { dateTime: string; timeZone: string }
    recurrence?: Record<string, unknown>
    extensions?: { pool?: string; wfStatus?: string; triggerRef?: string; epicKey?: string; source?: 'microsoft-todo' | 'jira' | 'triggertodo' }
  },
) {
  return request<TodoTask>(`/api/todo/lists/${listId}/tasks`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateTask(
  listId: string,
  taskId: string,
  payload: Record<string, unknown>,
) {
  return request<TodoTask>(`/api/todo/lists/${listId}/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function updateTaskById(taskId: string, payload: Record<string, unknown>) {
  return request<TodoTask>(`/api/todo/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteTask(listId: string, taskId: string) {
  return request<{ ok: boolean }>(`/api/todo/lists/${listId}/tasks/${taskId}`, {
    method: 'DELETE',
  })
}

export async function completeTask(listId: string, taskId: string) {
  return request(`/api/todo/lists/${listId}/tasks/${taskId}/complete`, {
    method: 'POST',
  })
}

export async function queryCachedTasks(params?: { pool?: string; wfStatus?: string }) {
  const search = new URLSearchParams()
  if (params?.pool) search.set('pool', params.pool)
  if (params?.wfStatus) search.set('wf_status', params.wfStatus)
  return request<{
    count: number
    items: Array<{
      listId: string
      taskId: string
      title: string
      pool?: string
      wfStatus?: string
      status?: string
      importance?: string
      bodyContent?: string
      dueDateTime?: string
      dueTimeZone?: string
      recurrenceJson?: string
      triggerRef?: string
      epicKey?: string
      createdDateTime?: string
      lastModifiedDateTime?: string
      source?: 'microsoft-todo' | 'jira' | 'triggertodo'
    }>
  }>(`/api/todo/cache/tasks${search.toString() ? `?${search.toString()}` : ''}`)
}

export async function syncDelta() {
  return request<{ ok: boolean; lists_synced?: number; tasks_synced?: number }>('/api/sync/delta', {
    method: 'POST',
  })
}

export async function listEpics() {
  return request<{
    count: number
    items: Array<{
      id: number
      epic_key: string
      name: string
      status?: string
      priority?: string
      updated_at: string
    }>
  }>('/api/epics')
}

export async function createEpic(payload: {
  epic_key: string
  name: string
  status?: string
  priority?: string
}) {
  return request<{
    id: number
    epic_key: string
    name: string
    status?: string
    priority?: string
    updated_at: string
  }>('/api/epics', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateEpic(epicId: number, payload: { name?: string; status?: string; priority?: string }) {
  return request<{
    id: number
    epic_key: string
    name: string
    status?: string
    priority?: string
    updated_at: string
  }>(`/api/epics/${epicId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function listTriggerRules() {
  return request<{ count: number; items: TriggerRule[] }>('/api/triggers')
}

export async function createTriggerRule(payload: {
  name: string
  source_pool?: string
  source_wf_status?: string
  target_pool?: string
  target_wf_status?: string
  enabled: boolean
  cron_expression?: string
}) {
  return request<TriggerRule>('/api/triggers', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateTriggerRule(ruleId: number, payload: Record<string, unknown>) {
  return request<TriggerRule>(`/api/triggers/${ruleId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteTriggerRule(ruleId: number) {
  return request<{ ok: boolean }>(`/api/triggers/${ruleId}`, {
    method: 'DELETE',
  })
}

export async function runTriggersNow() {
  return request('/api/triggers/run', { method: 'POST' })
}

export async function monitorTriggers() {
  return request<{
    count: number
    items: TriggerRuleWithMonitor[]
    unassignedTasks: number
    orphanTriggerRefs: string[]
  }>('/api/triggers/monitor')
}

export async function listTriggerEvents() {
  return request<{ count: number; items: TriggerEvent[] }>('/api/events')
}

export async function createTriggerEvent(payload: { name: string }) {
  return request<TriggerEvent>('/api/events', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateTriggerEvent(eventId: number, payload: { name?: string; is_active?: boolean }) {
  return request<TriggerEvent>(`/api/events/${eventId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteTriggerEvent(eventId: number) {
  return request<{ ok: boolean }>(`/api/events/${eventId}`, {
    method: 'DELETE',
  })
}

export async function listJiraEpics(projectKey: string, maxResults = 50) {
  return request<{
    project: string
    total: number
    count: number
    issues: Array<{
      id: string
      key: string
      source: 'jira'
      summary: string
      status?: string
      priority?: string
      issueType?: string
      parentKey?: string
    }>
  }>(`/api/jira/projects/${encodeURIComponent(projectKey)}/epics?max_results=${maxResults}`)
}

export async function listJiraIssues(projectKey: string, maxResults = 100) {
  return request<{
    project: string
    total: number
    count: number
    issues: Array<{
      id: string
      key: string
      source: 'jira'
      summary: string
      status?: string
      priority?: string
      issueType?: string
      parentKey?: string
    }>
  }>(`/api/jira/projects/${encodeURIComponent(projectKey)}/issues?max_results=${maxResults}`)
}

export async function updateJiraIssue(issueKey: string, payload: { summary?: string }) {
  return request<{ ok: boolean; issueKey: string }>(`/api/jira/issues/${encodeURIComponent(issueKey)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
