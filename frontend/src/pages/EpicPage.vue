<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createEpic, listEpics, listTriggerEvents, queryCachedTasks, updateEpic } from '../lib/api'
import { hasAnyTriggerConfigured, isTaskTriggered } from '../lib/triggerSignal'
import type { TodoTask, TriggerEvent } from '../lib/types'

type EpicRow = {
  id: number
  key: string
  name: string
  status?: string
  priorityTag: 'P0' | 'P1' | 'P2' | 'P3'
  linkedTasks: number
  saving?: boolean
}

const loading = ref(false)
const router = useRouter()
const editMode = ref(false)
const rows = ref<EpicRow[]>([])
const creating = ref(false)
const editDialogVisible = ref(false)
const savingEdit = ref(false)
const isMobile = ref(false)
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
const linkedTasksDialogVisible = ref(false)
const linkedTasks = ref<
  Array<{
    taskId: string
    listId: string
    title: string
    wfStatus?: string
    workflowDisplay: string
    triggerRef?: string
    triggerDisplay: string
  }>
>([])
const tasksByEpicKey = ref(
  new Map<
    string,
    Array<{
      taskId: string
      listId: string
      title: string
      wfStatus?: string
      workflowDisplay: string
      triggerRef?: string
      triggerDisplay: string
    }>
  >(),
)

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
const linkedTasksDialogWidth = computed(() => (isMobile.value ? '92vw' : '760px'))

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

function effectiveWorkflowStatus(
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
): string {
  const normalized = normalizeWorkflowStatus(item.wfStatus)
  if (normalized === 'missing-trigger') return normalized
  const task = toSignalTask(item)
  if (!hasAnyTriggerConfigured(task)) return 'missing-trigger'
  if (hasAnyTriggerConfigured(task) && !isTaskTriggered(task, eventsById)) return 'wait-for-trigger'
  return normalized || '-'
}

async function loadEpics() {
  loading.value = true
  try {
    const [epicsData, tasksData, eventsData] = await Promise.all([listEpics(), queryCachedTasks(), listTriggerEvents()])
    const eventsById = new Map<number, TriggerEvent>(eventsData.items.map((event) => [event.id, event]))
    const linkedByEpic = new Map<string, number>()
    const taskMap = new Map<
      string,
      Array<{
        taskId: string
        listId: string
        title: string
        wfStatus?: string
        workflowDisplay: string
        triggerRef?: string
        triggerDisplay: string
      }>
    >()

    for (const task of tasksData.items) {
      if (String(task.status || '').toLowerCase() === 'completed') continue
      const epicKey = String(task.epicKey || '').trim().toUpperCase()
      if (!epicKey) continue
      linkedByEpic.set(epicKey, (linkedByEpic.get(epicKey) || 0) + 1)
      const tasks = taskMap.get(epicKey) || []
      tasks.push({
        taskId: task.taskId,
        listId: task.listId,
        title: task.title,
        wfStatus: task.wfStatus,
        workflowDisplay: effectiveWorkflowStatus(task, eventsById),
        triggerRef: task.triggerRef,
        triggerDisplay: triggerLabel(task.triggerRef, eventsById),
      })
      taskMap.set(epicKey, tasks)
    }
    tasksByEpicKey.value = taskMap

    rows.value = epicsData.items
      .filter((item) => !isCompletedStatus(item.status))
      .map((item) => ({
        id: item.id,
        key: item.epic_key,
        name: item.name,
        status: item.status,
        priorityTag: normalizePriorityTag(item.priority),
        linkedTasks: linkedByEpic.get(String(item.epic_key || '').toUpperCase()) || 0,
      }))
      .sort((a, b) => {
        const rankDiff = priorityRank(a.priorityTag) - priorityRank(b.priorityTag)
        if (rankDiff !== 0) return rankDiff
        return a.key.localeCompare(b.key)
      })
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load epics')
  } finally {
    loading.value = false
  }
}

function openLinkedTasks(row: EpicRow) {
  const epicKey = String(row.key || '').trim().toUpperCase()
  linkedTasks.value = tasksByEpicKey.value.get(epicKey) || []
  linkedTasksDialogVisible.value = true
}

function viewTask(task: { listId: string; taskId: string }) {
  linkedTasksDialogVisible.value = false
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
        <strong>Epics</strong>
      </template>
      <el-table :data="rows" empty-text="No epics found" class="epic-table">
        <el-table-column label="Name" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <div class="epic-name-cell">
              <span class="epic-name-text">{{ scope.row.name }}</span>
              <el-tag v-if="isMobile" size="small" effect="dark" :type="priorityTagType(scope.row.priorityTag)">{{ scope.row.priorityTag }}</el-tag>
              <el-button v-if="editMode" size="small" type="primary" @click="openEdit(scope.row)">Edit</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="!isMobile" label="Priority" width="110">
          <template #default="scope">
            <el-tag effect="dark" :type="priorityTagType(scope.row.priorityTag)">{{ scope.row.priorityTag }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Linked" :width="isMobile ? 76 : 90">
          <template #default="scope">
            <el-button
              v-if="scope.row.linkedTasks > 0"
              link
              type="success"
              class="linked-tag"
              @click="openLinkedTasks(scope.row)"
            >
              {{ scope.row.linkedTasks }}
            </el-button>
            <el-tag v-else effect="plain" type="info" class="linked-tag">0</el-tag>
          </template>
        </el-table-column>
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

    <el-dialog v-model="linkedTasksDialogVisible" title="Linked Tasks" :width="linkedTasksDialogWidth">
      <el-table :data="linkedTasks" empty-text="No linked tasks">
        <el-table-column prop="title" label="Task" min-width="260" show-overflow-tooltip />
        <el-table-column label="Workflow" width="130">
          <template #default="scope">
            <el-tag effect="plain">{{ workflowLabel(scope.row.workflowDisplay) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Trigger" min-width="130" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.triggerDisplay }}
          </template>
        </el-table-column>
        <el-table-column label="Action" width="90">
          <template #default="scope">
            <el-button link type="primary" @click="viewTask(scope.row)">Open</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </section>
</template>
