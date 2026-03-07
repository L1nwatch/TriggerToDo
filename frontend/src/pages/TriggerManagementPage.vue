<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import TaskEditDialog from '../components/TaskEditDialog.vue'
import { listEpics, listTodoLists, listTriggerEvents, queryCachedTasks, updateTask } from '../lib/api'
import { isOnOrAfterBoardCutoff } from '../lib/boardCutoff'
import { builtInTriggerOptions, DATE_TRIGGER_REFS, dateTriggerLabel, isDateTriggerRef } from '../lib/triggerCatalog'
import { isTaskTriggered } from '../lib/triggerSignal'
import { defaultTaskForm, formFromTask, taskPayloadFromForm, type TaskFormModel } from '../lib/taskForm'
import type { TodoList, TodoTask, TriggerEvent } from '../lib/types'

const loading = ref(false)
const saving = ref(false)
const triggerLoading = ref(false)
const epicLoading = ref(false)
const events = ref<TriggerEvent[]>([])
const tasks = ref<TodoTask[]>([])
const lists = ref<TodoList[]>([])
const epicOptions = ref<Array<{ value: string; label: string }>>([])
const expandedTriggerKeys = ref<string[]>([])
const editDialogVisible = ref(false)
const editingTask = ref<TodoTask | null>(null)
const editForm = ref<TaskFormModel>(defaultTaskForm(''))

function cacheItemToTask(item: {
  listId: string
  taskId: string
  title: string
  status?: string
  importance?: string
  bodyContent?: string
  dueDateTime?: string
  dueTimeZone?: string
  recurrenceJson?: string
  pool?: string
  wfStatus?: string
  triggerRef?: string
  createdDateTime?: string
  lastModifiedDateTime?: string
  source?: 'microsoft-todo' | 'jira' | 'triggertodo'
}): TodoTask {
  return {
    id: item.taskId,
    listId: item.listId,
    title: item.title,
    status: item.status,
    importance: item.importance,
    source: item.source || 'microsoft-todo',
    createdDateTime: item.createdDateTime || null,
    lastModifiedDateTime: item.lastModifiedDateTime || null,
    body: { contentType: 'text', content: item.bodyContent || '' },
    dueDateTime: item.dueDateTime ? { dateTime: item.dueDateTime, timeZone: item.dueTimeZone || 'UTC' } : null,
    recurrence: item.recurrenceJson
      ? (JSON.parse(item.recurrenceJson) as { pattern: Record<string, unknown>; range: Record<string, unknown> })
      : null,
    extensions: [
      {
        extensionName: 'com.triggertodo.meta',
        pool: item.pool || null,
        wfStatus: item.wfStatus || null,
        triggerRef: item.triggerRef || null,
        source: item.source || 'microsoft-todo',
      },
    ],
  }
}

const eventsById = computed(() => new Map<number, TriggerEvent>(events.value.map((event) => [event.id, event])))

const openTasks = computed(() =>
  tasks.value.filter((task) => String(task.status || '').toLowerCase() !== 'completed' && isOnOrAfterBoardCutoff(task)),
)

function triggerRef(task: TodoTask) {
  const ext = task.extensions?.find((item) => item.extensionName === 'com.triggertodo.meta')
  return String(ext?.triggerRef || '').trim()
}

const eventTriggerRows = computed(() =>
  events.value.map((event) => {
    const matchedTasks = openTasks.value.filter((task) => triggerRef(task) === `event:${event.id}`)
    const relatedTasks = sortRelatedTasks(matchedTasks)
    const triggered = relatedTasks.filter((task) => task.triggered).length
    return {
      key: `event:${event.id}`,
      name: event.name,
      type: 'event-trigger',
      state: event.is_active ? 'occurred' : 'waiting-event',
      totalTasks: relatedTasks.length,
      triggeredTasks: triggered,
      waitingTasks: relatedTasks.length - triggered,
      occurredAt: event.occurred_at,
      relatedTasks,
    }
  }),
)

interface RelatedTask extends TodoTask {
  triggered: boolean
}

interface TriggerRow {
  key: string
  name: string
  type: string
  state: string
  totalTasks: number
  triggeredTasks: number
  waitingTasks: number
  occurredAt?: string | null
  relatedTasks: RelatedTask[]
}

function dueAt(task: TodoTask): number {
  const value = task.dueDateTime?.dateTime
  if (!value) return Number.POSITIVE_INFINITY
  const at = new Date(value).getTime()
  return Number.isNaN(at) ? Number.POSITIVE_INFINITY : at
}

function importanceRank(task: TodoTask): number {
  if (task.importance === 'high') return 0
  if (task.importance === 'normal') return 1
  if (task.importance === 'low') return 2
  return 3
}

function sortRelatedTasks(tasksToSort: TodoTask[]): RelatedTask[] {
  return tasksToSort
    .map((task) => ({ ...task, triggered: isTaskTriggered(task, eventsById.value) }))
    .sort((a, b) => {
      if (a.triggered !== b.triggered) return Number(b.triggered) - Number(a.triggered)
      const dueDiff = dueAt(a) - dueAt(b)
      if (dueDiff !== 0) return dueDiff
      const importanceDiff = importanceRank(a) - importanceRank(b)
      if (importanceDiff !== 0) return importanceDiff
      return a.title.localeCompare(b.title)
    })
}

const triggerRows = computed(() => {
  const rows: TriggerRow[] = DATE_TRIGGER_REFS.map((ref) => {
    const matched = openTasks.value.filter((task) => {
      const taskRef = triggerRef(task)
      if (ref === 'date') {
        return taskRef === 'date' || (!taskRef && Boolean(task.dueDateTime?.dateTime))
      }
      return taskRef === ref
    })
    const relatedTasks = sortRelatedTasks(matched)
    const triggered = relatedTasks.filter((task) => task.triggered).length
    return {
      key: ref,
      name: dateTriggerLabel(ref),
      type: 'date-trigger',
      state: 'time-based',
      totalTasks: relatedTasks.length,
      triggeredTasks: triggered,
      waitingTasks: relatedTasks.length - triggered,
      occurredAt: null as string | null,
      relatedTasks,
    }
  })
  rows.push(...eventTriggerRows.value)
  return rows.sort((a, b) => b.totalTasks - a.totalTasks || a.name.localeCompare(b.name))
})

const overview = computed(() => ({
  totalTriggers: DATE_TRIGGER_REFS.length + events.value.length,
  dateTriggers: DATE_TRIGGER_REFS.length,
  eventTriggers: events.value.length,
  activeEvents: events.value.filter((event) => event.is_active).length,
  totalAssignedTasks: triggerRows.value.reduce((acc, row) => acc + row.totalTasks, 0),
  totalTriggeredTasks: triggerRows.value.reduce((acc, row) => acc + row.triggeredTasks, 0),
  totalWaitingTasks: triggerRows.value.reduce((acc, row) => acc + row.waitingTasks, 0),
}))

function typeTagType(type: string) {
  if (type === 'date-trigger') return 'success'
  if (type === 'event-trigger') return 'warning'
  return 'info'
}

function stateTagType(state: string) {
  if (state === 'occurred') return 'success'
  if (state === 'waiting-event') return 'warning'
  return 'info'
}

function taskStateTagType(triggered: boolean) {
  return triggered ? 'success' : 'warning'
}

function taskStatusTagType(status?: string) {
  const value = String(status || '').toLowerCase()
  if (value === 'completed') return 'success'
  if (value.includes('progress')) return 'primary'
  if (value === 'notstarted') return 'info'
  return 'info'
}

function statusLabel(status?: string) {
  return String(status || 'open').trim() || 'open'
}

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const at = new Date(value)
  return Number.isNaN(at.getTime()) ? '-' : at.toLocaleString()
}

function formatDue(value?: string | null) {
  if (!value) return 'No due date'
  const at = new Date(value)
  return Number.isNaN(at.getTime()) ? 'No due date' : at.toLocaleString()
}

function toggleTriggerRow(row: TriggerRow) {
  if (expandedTriggerKeys.value.includes(row.key)) {
    expandedTriggerKeys.value = expandedTriggerKeys.value.filter((key) => key !== row.key)
    return
  }
  expandedTriggerKeys.value = [...expandedTriggerKeys.value, row.key]
}

function syncExpandedRows(_: TriggerRow, expandedRows: TriggerRow[]) {
  expandedTriggerKeys.value = expandedRows.map((item) => item.key)
}

function openTask(task: TodoTask) {
  editingTask.value = task
  editForm.value = formFromTask(task)
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editingTask.value) return
  if (!editForm.value.title.trim()) {
    ElMessage.warning('Title is required')
    return
  }
  if (isDateTriggerRef(editForm.value.triggerRef) && !editForm.value.dueAt) {
    ElMessage.warning('Date trigger requires due date')
    return
  }
  saving.value = true
  try {
    await updateTask(editingTask.value.listId, editingTask.value.id, taskPayloadFromForm(editForm.value))
    editDialogVisible.value = false
    await loadData()
    ElMessage.success('Task updated')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update task')
  } finally {
    saving.value = false
  }
}

async function loadData() {
  loading.value = true
  triggerLoading.value = true
  epicLoading.value = true
  try {
    const [eventsResult, cache, listsResult, epicsResult] = await Promise.all([
      listTriggerEvents(),
      queryCachedTasks(),
      listTodoLists(),
      listEpics(),
    ])
    events.value = eventsResult.items
    tasks.value = cache.items.map(cacheItemToTask)
    lists.value = listsResult
    epicOptions.value = epicsResult.items.map((epic) => ({
      value: epic.epic_key,
      label: epic.name || 'Unnamed Epic',
    }))
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load trigger management data')
  } finally {
    triggerLoading.value = false
    epicLoading.value = false
    loading.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <section class="page-shell trigger-page">
    <header class="page-head trigger-head">
      <div>
        <h1>Trigger Management</h1>
        <p>Overview of date-trigger and event-trigger status across your tasks</p>
      </div>
    </header>

    <el-row :gutter="12" class="monitor-cards trigger-kpis">
      <el-col :xs="12" :md="6">
        <el-card class="kpi-card kpi-a">
          <p class="metric-label">Total Triggers</p>
          <p class="metric-value">{{ overview.totalTriggers }}</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="kpi-card kpi-b">
          <p class="metric-label">Date Triggers</p>
          <p class="metric-value">{{ overview.dateTriggers }}</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="kpi-card kpi-c">
          <p class="metric-label">Event Triggers</p>
          <p class="metric-value">{{ overview.eventTriggers }}</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="kpi-card kpi-d">
          <p class="metric-label">Active Events</p>
          <p class="metric-value">{{ overview.activeEvents }}</p>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="monitor-cards trigger-kpis trigger-kpis-secondary">
      <el-col :xs="12" :md="6">
        <el-card class="kpi-card">
          <p class="metric-label">Assigned Tasks</p>
          <p class="metric-value">{{ overview.totalAssignedTasks }}</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="kpi-card kpi-triggered">
          <p class="metric-label">Triggered</p>
          <p class="metric-value">{{ overview.totalTriggeredTasks }}</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="kpi-card kpi-waiting">
          <p class="metric-label">Waiting</p>
          <p class="metric-value">{{ overview.totalWaitingTasks }}</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="kpi-card">
          <p class="metric-label">Events</p>
          <p class="metric-value">{{ events.length }}</p>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="settings-block trigger-table-wrap" v-loading="loading">
      <template #header>
        <div class="trigger-table-header">
          <strong>Trigger status by trigger</strong>
          <span>Click a trigger row to expand its related tasks.</span>
        </div>
      </template>
      <el-table
        :data="triggerRows"
        row-key="key"
        :expand-row-keys="expandedTriggerKeys"
        empty-text="No triggers yet"
        @row-click="toggleTriggerRow"
        @expand-change="syncExpandedRows"
      >
        <el-table-column type="expand" width="52">
          <template #default="scope">
            <div class="trigger-detail">
              <div class="trigger-detail-head">
                <strong>{{ scope.row.relatedTasks.length }} related tasks</strong>
                <span>Triggered tasks are shown first.</span>
              </div>
              <div v-if="scope.row.relatedTasks.length" class="trigger-task-list">
                <article v-for="task in scope.row.relatedTasks" :key="task.id" class="trigger-task-item">
                  <el-button link class="trigger-task-link" @click.stop="openTask(task)">
                    {{ task.title }}
                  </el-button>
                  <div class="trigger-task-meta">
                    <el-tag size="small" effect="light" :type="taskStateTagType(task.triggered)">
                      {{ task.triggered ? 'triggered' : 'waiting' }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="taskStatusTagType(task.status)">
                      {{ statusLabel(task.status) }}
                    </el-tag>
                    <el-tag v-if="task.importance === 'high'" size="small" effect="plain" type="danger">
                      high priority
                    </el-tag>
                    <span class="trigger-task-due">{{ formatDue(task.dueDateTime?.dateTime) }}</span>
                  </div>
                </article>
              </div>
              <el-empty v-else description="No open tasks use this trigger." :image-size="72" />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="Trigger" min-width="220" />
        <el-table-column label="Type" width="140">
          <template #default="scope">
            <el-tag size="small" effect="light" :type="typeTagType(scope.row.type)">{{ scope.row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="State" width="140">
          <template #default="scope">
            <el-tag size="small" effect="light" :type="stateTagType(scope.row.state)">{{ scope.row.state }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="totalTasks" label="Tasks" width="90" />
        <el-table-column prop="triggeredTasks" label="Triggered" width="100" />
        <el-table-column prop="waitingTasks" label="Waiting" width="90" />
        <el-table-column label="Last occurred" min-width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.occurredAt) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <TaskEditDialog
      v-model="editDialogVisible"
      :model="editForm"
      :lists="lists"
      :readonly-list="true"
      :hide-workflow-status="true"
      :saving="saving"
      :trigger-options="[
        ...builtInTriggerOptions(),
        ...events.map((event) => ({ value: `event:${event.id}`, label: `event-trigger: ${event.name}${event.is_active ? ' (occurred)' : ''}` })),
      ]"
      :trigger-loading="triggerLoading"
      :epic-options="epicOptions"
      :epic-loading="epicLoading"
      @save="submitEdit"
    />
  </section>
</template>
