<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createEpic, listEpics, listTriggerEvents, queryCachedTasks, updateEpic } from '../lib/api'
import { hasAnyTriggerConfigured, isTaskTriggered } from '../lib/triggerSignal'
import type { TodoTask, TriggerEvent } from '../lib/types'

type RelatedEpicTask = {
  taskId: string
  listId: string
  title: string
  status?: string
  importance?: string
  dueDateTime?: string
  wfStatus?: string
  workflowDisplay: string
  triggerRef?: string
  triggerDisplay: string
  triggered: boolean
}

type EpicRow = {
  id: number
  key: string
  name: string
  status?: string
  priorityTag: 'P0' | 'P1' | 'P2' | 'P3'
  linkedTasks: number
  triggeredTasks: number
  waitingTasks: number
  relatedTasks: RelatedEpicTask[]
}

const loading = ref(false)
const router = useRouter()
const editMode = ref(false)
const rows = ref<EpicRow[]>([])
const creating = ref(false)
const editDialogVisible = ref(false)
const savingEdit = ref(false)
const isMobile = ref(false)
const expandedEpicKeys = ref<string[]>([])
let mobileMediaQuery: MediaQueryList | null = null
const editEpic = ref<{
  id: number
  key: string
  name: string
  priorityTag: 'P0' | 'P1' | 'P2' | 'P3'
} | null>(null)
const newEpic = ref<{
  name: string
  priorityTag: 'P0' | 'P1' | 'P2' | 'P3'
}>({
  name: '',
  priorityTag: 'P2',
})

function isCompletedStatus(status?: string) {
  const value = (status || '').toLowerCase()
  return value.includes('done') || value.includes('closed') || value.includes('resolved') || value.includes('complete')
}

function normalizePriorityTag(priority?: string): 'P0' | 'P1' | 'P2' | 'P3' {
  const value = (priority || '').toLowerCase()
  if (value.includes('p0') || value.includes('highest') || value.includes('critical') || value.includes('blocker')) return 'P0'
  if (value.includes('p1') || value.includes('high') || value.includes('major')) return 'P1'
  if (value.includes('p2') || value.includes('medium') || value.includes('normal')) return 'P2'
  if (value.includes('p3') || value.includes('low') || value.includes('minor')) return 'P3'
  return 'P2'
}

function priorityRank(priorityTag: 'P0' | 'P1' | 'P2' | 'P3') {
  if (priorityTag === 'P0') return 0
  if (priorityTag === 'P1') return 1
  if (priorityTag === 'P2') return 2
  if (priorityTag === 'P3') return 3
  return 9
}

function priorityTagType(priorityTag: 'P0' | 'P1' | 'P2' | 'P3') {
  if (priorityTag === 'P0') return 'danger'
  if (priorityTag === 'P1') return 'warning'
  if (priorityTag === 'P2') return 'success'
  return 'info'
}

const total = computed(() => rows.value.length)
const highPriorityCount = computed(() => rows.value.filter((row) => row.priorityTag === 'P0' || row.priorityTag === 'P1').length)
const linkedTaskTotal = computed(() => rows.value.reduce((sum, row) => sum + row.linkedTasks, 0))
const editDialogWidth = computed(() => (isMobile.value ? '92vw' : '560px'))

function normalizeWorkflowStatus(raw?: string): string {
  const value = String(raw || '').trim().toLowerCase()
  if (!value) return ''
  if (value === 'wait-for-trigger' || value === 'wait trigger' || value === 'wait-trigger' || value === 'wait for trigger') {
    return 'wait-for-trigger'
  }
  if (value === 'missing-trigger' || value === 'missing trigger') return 'missing-trigger'
  if (value === 'todo' || value === 'doing') return value
  return value
}

function workflowLabel(value: string): string {
  if (value === 'wait-for-trigger') return 'Pending Trigger'
  if (value === 'missing-trigger') return 'Missing Trigger'
  return value || '-'
}

function triggerLabel(ref: string | undefined, eventsById: Map<number, TriggerEvent>): string {
  const value = String(ref || '').trim()
  if (!value) return 'Missing Trigger'
  const lower = value.toLowerCase()
  if (lower.startsWith('event:')) {
    const id = Number(lower.slice('event:'.length))
    const eventName = Number.isFinite(id) ? eventsById.get(id)?.name : ''
    return eventName ? `Event: ${eventName}` : value
  }
  if (lower === 'date') return 'Date Trigger'
  if (lower.startsWith('date:')) return `Date Trigger (${lower.slice('date:'.length)})`
  return value
}

function toSignalTask(item: {
  taskId: string
  listId: string
  title: string
  dueDateTime?: string
  dueTimeZone?: string
  recurrenceJson?: string
  triggerRef?: string
}): TodoTask {
  let recurrence: TodoTask['recurrence'] = null
  if (item.recurrenceJson) {
    try {
      recurrence = JSON.parse(item.recurrenceJson) as TodoTask['recurrence']
    } catch {
      recurrence = null
    }
  }
  return {
    id: item.taskId,
    listId: item.listId,
    title: item.title,
    source: 'triggertodo',
    dueDateTime: item.dueDateTime
      ? { dateTime: item.dueDateTime, timeZone: item.dueTimeZone || 'UTC' }
      : null,
    recurrence,
    extensions: [
      {
        extensionName: 'com.triggertodo.meta',
        triggerRef: item.triggerRef || null,
      },
    ],
  }
}

function workflowTagType(value: string) {
  if (value === 'missing-trigger') return 'danger'
  if (value === 'wait-for-trigger') return 'warning'
  if (value === '-') return 'info'
  return 'success'
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

function formatDue(value?: string | null) {
  if (!value) return 'No due date'
  const at = new Date(value)
  return Number.isNaN(at.getTime()) ? 'No due date' : at.toLocaleString()
}

function dueAt(task: RelatedEpicTask): number {
  if (!task.dueDateTime) return Number.POSITIVE_INFINITY
  const at = new Date(task.dueDateTime).getTime()
  return Number.isNaN(at) ? Number.POSITIVE_INFINITY : at
}

function importanceRank(importance?: string): number {
  if (importance === 'high') return 0
  if (importance === 'normal') return 1
  if (importance === 'low') return 2
  return 3
}

function taskSignalState(
  item: {
    taskId: string
    listId: string
    title: string
    wfStatus?: string
    dueDateTime?: string
    dueTimeZone?: string
    recurrenceJson?: string
    triggerRef?: string
  },
  eventsById: Map<number, TriggerEvent>,
): { triggered: boolean; workflowDisplay: string } {
  const normalized = normalizeWorkflowStatus(item.wfStatus)
  const task = toSignalTask(item)
  const hasTrigger = hasAnyTriggerConfigured(task)
  const triggered = hasTrigger && isTaskTriggered(task, eventsById)

  if (normalized === 'missing-trigger' || !hasTrigger) {
    return {
      triggered: false,
      workflowDisplay: 'missing-trigger',
    }
  }
  if (!triggered) {
    return {
      triggered: false,
      workflowDisplay: 'wait-for-trigger',
    }
  }
  return {
    triggered: true,
    workflowDisplay: normalized || '-',
  }
}

function sortRelatedTasks(tasks: RelatedEpicTask[]) {
  return [...tasks].sort((a, b) => {
    if (a.triggered !== b.triggered) return Number(b.triggered) - Number(a.triggered)
    const dueDiff = dueAt(a) - dueAt(b)
    if (dueDiff !== 0) return dueDiff
    const importanceDiff = importanceRank(a.importance) - importanceRank(b.importance)
    if (importanceDiff !== 0) return importanceDiff
    return a.title.localeCompare(b.title)
  })
}

async function loadEpics() {
  loading.value = true
  try {
    const [epicsData, tasksData, eventsData] = await Promise.all([listEpics(), queryCachedTasks(), listTriggerEvents()])
    const eventsById = new Map<number, TriggerEvent>(eventsData.items.map((event) => [event.id, event]))
    const taskMap = new Map<string, RelatedEpicTask[]>()

    for (const task of tasksData.items) {
      if (String(task.status || '').toLowerCase() === 'completed') continue
      const epicKey = String(task.epicKey || '').trim().toUpperCase()
      if (!epicKey) continue
      const tasks = taskMap.get(epicKey) || []
      const signalState = taskSignalState(task, eventsById)
      tasks.push({
        taskId: task.taskId,
        listId: task.listId,
        title: task.title,
        status: task.status,
        importance: task.importance,
        dueDateTime: task.dueDateTime,
        wfStatus: task.wfStatus,
        workflowDisplay: signalState.workflowDisplay,
        triggerRef: task.triggerRef,
        triggerDisplay: triggerLabel(task.triggerRef, eventsById),
        triggered: signalState.triggered,
      })
      taskMap.set(epicKey, tasks)
    }

    rows.value = epicsData.items
      .filter((item) => !isCompletedStatus(item.status))
      .map((item) => {
        const relatedTasks = sortRelatedTasks(taskMap.get(String(item.epic_key || '').toUpperCase()) || [])
        const triggeredTasks = relatedTasks.filter((task) => task.triggered).length
        return {
          id: item.id,
          key: item.epic_key,
          name: item.name,
          status: item.status,
          priorityTag: normalizePriorityTag(item.priority),
          linkedTasks: relatedTasks.length,
          triggeredTasks,
          waitingTasks: relatedTasks.length - triggeredTasks,
          relatedTasks,
        }
      })
      .sort((a, b) => {
        const rankDiff = priorityRank(a.priorityTag) - priorityRank(b.priorityTag)
        if (rankDiff !== 0) return rankDiff
        return a.key.localeCompare(b.key)
      })
    expandedEpicKeys.value = expandedEpicKeys.value.filter((key) => rows.value.some((row) => row.key === key))
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load epics')
  } finally {
    loading.value = false
  }
}

function toggleEpicRow(row: EpicRow) {
  if (expandedEpicKeys.value.includes(row.key)) {
    expandedEpicKeys.value = expandedEpicKeys.value.filter((key) => key !== row.key)
    return
  }
  expandedEpicKeys.value = [...expandedEpicKeys.value, row.key]
}

function syncExpandedRows(_: EpicRow, expandedRows: EpicRow[]) {
  expandedEpicKeys.value = expandedRows.map((item) => item.key)
}

function viewTask(task: { listId: string; taskId: string }) {
  router.push({
    name: 'task-detail',
    params: {
      listId: task.listId,
      taskId: task.taskId,
    },
  })
}

function openEdit(row: EpicRow) {
  editEpic.value = {
    id: row.id,
    key: row.key,
    name: row.name,
    priorityTag: row.priorityTag,
  }
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editEpic.value) return
  const name = editEpic.value.name.trim()
  if (!name) {
    ElMessage.warning('Epic name is required')
    return
  }

  savingEdit.value = true
  try {
    await updateEpic(editEpic.value.id, { name, priority: editEpic.value.priorityTag })
    ElMessage.success('Epic updated')
    editDialogVisible.value = false
    editEpic.value = null
    await loadEpics()
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update epic')
  } finally {
    savingEdit.value = false
  }
}

async function submitNewEpic() {
  if (!editMode.value) {
    ElMessage.warning('Enable Edit Mode to add epics')
    return
  }

  const name = newEpic.value.name.trim()

  if (!name) {
    ElMessage.warning('Epic name is required')
    return
  }

  creating.value = true
  try {
    await createEpic({
      name,
      priority: newEpic.value.priorityTag,
      status: 'Open',
    })
    ElMessage.success('Epic created')
    newEpic.value = { name: '', priorityTag: 'P2' }
    await loadEpics()
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to create epic')
  } finally {
    creating.value = false
  }
}

onMounted(loadEpics)

function syncMobileLayout() {
  if (!mobileMediaQuery) return
  isMobile.value = mobileMediaQuery.matches
}

onMounted(() => {
  mobileMediaQuery = window.matchMedia('(max-width: 900px)')
  syncMobileLayout()
  mobileMediaQuery.addEventListener('change', syncMobileLayout)
})

onBeforeUnmount(() => {
  mobileMediaQuery?.removeEventListener('change', syncMobileLayout)
})
</script>

<template>
  <section class="page-shell epic-page">
    <header class="page-head">
      <div>
        <h1>Epics</h1>
        <p>{{ total }} active epic(s)</p>
      </div>
      <div class="actions">
        <el-button @click="editMode = !editMode" :type="editMode ? 'warning' : 'default'">
          {{ editMode ? 'Exit Edit Mode' : 'Edit Mode' }}
        </el-button>
      </div>
    </header>

    <section class="epic-kpis">
      <article class="epic-kpi-card epic-kpi-total">
        <p class="metric-label">Active Epics</p>
        <p class="metric-value">{{ total }}</p>
      </article>
      <article class="epic-kpi-card epic-kpi-priority">
        <p class="metric-label">High Priority</p>
        <p class="metric-value">{{ highPriorityCount }}</p>
      </article>
      <article class="epic-kpi-card epic-kpi-linked">
        <p class="metric-label">Linked Tasks</p>
        <p class="metric-value">{{ linkedTaskTotal }}</p>
      </article>
    </section>

    <el-card v-if="editMode">
      <template #header>
        <strong>Create Epic</strong>
      </template>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="Epic name">
          <el-input v-model="newEpic.name" placeholder="Epic name" clearable />
        </el-form-item>
        <el-form-item label="Priority">
          <el-select v-model="newEpic.priorityTag" class="field-full">
            <el-option label="P0" value="P0" />
            <el-option label="P1" value="P1" />
            <el-option label="P2" value="P2" />
            <el-option label="P3" value="P3" />
          </el-select>
        </el-form-item>
        <div class="actions">
          <el-button type="primary" :loading="creating" @click="submitNewEpic">Create</el-button>
        </div>
      </el-form>
    </el-card>

    <el-card class="settings-block" v-loading="loading">
      <template #header>
        <div class="epic-table-header">
          <strong>Epic status by epic</strong>
          <span>Click an epic row to expand its related tasks.</span>
        </div>
      </template>
      <el-table
        :data="rows"
        row-key="key"
        :expand-row-keys="expandedEpicKeys"
        empty-text="No epics found"
        class="epic-table"
        @row-click="toggleEpicRow"
        @expand-change="syncExpandedRows"
      >
        <el-table-column type="expand" width="52">
          <template #default="scope">
            <div class="epic-detail">
              <div class="epic-detail-head">
                <strong>{{ scope.row.relatedTasks.length }} related tasks</strong>
                <span>Triggered tasks are shown first.</span>
              </div>
              <div v-if="scope.row.relatedTasks.length" class="epic-task-list">
                <article v-for="task in scope.row.relatedTasks" :key="task.taskId" class="epic-task-item">
                  <el-button link class="epic-task-link" @click.stop="viewTask(task)">
                    {{ task.title }}
                  </el-button>
                  <div class="epic-task-meta">
                    <el-tag size="small" effect="light" :type="taskStateTagType(task.triggered)">
                      {{ task.triggered ? 'triggered' : 'waiting' }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="workflowTagType(task.workflowDisplay)">
                      {{ workflowLabel(task.workflowDisplay) }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="taskStatusTagType(task.status)">
                      {{ statusLabel(task.status) }}
                    </el-tag>
                    <el-tag v-if="task.importance === 'high'" size="small" effect="plain" type="danger">
                      high priority
                    </el-tag>
                    <span class="epic-task-trigger">{{ task.triggerDisplay }}</span>
                    <span class="epic-task-due">{{ formatDue(task.dueDateTime) }}</span>
                  </div>
                </article>
              </div>
              <el-empty v-else description="No open tasks are linked to this epic." :image-size="72" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Name" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <div class="epic-name-cell">
              <div class="epic-name-stack">
                <span class="epic-name-text">{{ scope.row.name }}</span>
                <span class="epic-key-text">{{ scope.row.key }}</span>
              </div>
              <div class="epic-name-actions">
                <el-tag v-if="isMobile" size="small" effect="dark" :type="priorityTagType(scope.row.priorityTag)">{{ scope.row.priorityTag }}</el-tag>
                <el-button v-if="editMode" size="small" type="primary" @click.stop="openEdit(scope.row)">Edit</el-button>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="!isMobile" label="Priority" width="110">
          <template #default="scope">
            <el-tag effect="dark" :type="priorityTagType(scope.row.priorityTag)">{{ scope.row.priorityTag }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="linkedTasks" label="Tasks" :width="isMobile ? 76 : 90" />
        <el-table-column v-if="!isMobile" prop="triggeredTasks" label="Triggered" width="100" />
        <el-table-column v-if="!isMobile" prop="waitingTasks" label="Waiting" width="90" />
      </el-table>
    </el-card>

    <el-dialog v-model="editDialogVisible" title="Edit Epic" :width="editDialogWidth">
      <el-form v-if="editEpic" label-position="top" @submit.prevent>
        <el-form-item label="Epic name">
          <el-input v-model="editEpic.name" />
        </el-form-item>
        <el-form-item label="Priority">
          <el-select v-model="editEpic.priorityTag" class="field-full">
            <el-option label="P0" value="P0" />
            <el-option label="P1" value="P1" />
            <el-option label="P2" value="P2" />
            <el-option label="P3" value="P3" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="actions">
          <el-button @click="editDialogVisible = false">Cancel</el-button>
          <el-button type="primary" :loading="savingEdit" @click="submitEdit">Save</el-button>
        </div>
      </template>
    </el-dialog>

  </section>
</template>
