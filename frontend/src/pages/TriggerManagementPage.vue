<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listTriggerEvents, queryCachedTasks } from '../lib/api'
import { isOnOrAfterBoardCutoff } from '../lib/boardCutoff'
import { DATE_TRIGGER_REFS, dateTriggerLabel } from '../lib/triggerCatalog'
import { isTaskTriggered } from '../lib/triggerSignal'
import type { TodoTask, TriggerEvent } from '../lib/types'

const loading = ref(false)
const events = ref<TriggerEvent[]>([])
const tasks = ref<TodoTask[]>([])

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
    const triggered = matchedTasks.filter((task) => isTaskTriggered(task, eventsById.value)).length
    return {
      key: `event:${event.id}`,
      name: event.name,
      type: 'event-trigger',
      state: event.is_active ? 'occurred' : 'waiting-event',
      totalTasks: matchedTasks.length,
      triggeredTasks: triggered,
      waitingTasks: matchedTasks.length - triggered,
      occurredAt: event.occurred_at,
    }
  }),
)

interface TriggerRow {
  key: string
  name: string
  type: string
  state: string
  totalTasks: number
  triggeredTasks: number
  waitingTasks: number
  occurredAt?: string | null
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
    const triggered = matched.filter((task) => isTaskTriggered(task, eventsById.value)).length
    return {
      key: ref,
      name: dateTriggerLabel(ref),
      type: 'date-trigger',
      state: 'time-based',
      totalTasks: matched.length,
      triggeredTasks: triggered,
      waitingTasks: matched.length - triggered,
      occurredAt: null as string | null,
    }
  })
  rows.push(...eventTriggerRows.value)
  return rows.sort((a, b) => b.totalTasks - a.totalTasks)
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

async function loadData() {
  loading.value = true
  try {
    const [eventsResult, cache] = await Promise.all([listTriggerEvents(), queryCachedTasks()])
    events.value = eventsResult.items
    tasks.value = cache.items.map(cacheItemToTask)
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load trigger management data')
  } finally {
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
        <strong>Trigger status by trigger</strong>
      </template>
      <el-table :data="triggerRows" empty-text="No triggers yet">
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
            {{ scope.row.occurredAt ? new Date(scope.row.occurredAt).toLocaleString() : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>
