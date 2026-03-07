<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import TaskEditDialog from '../components/TaskEditDialog.vue'
import { completeTask, createTask, fetchAllTasks, listEpics, listTriggerEvents, updateTask, updateTaskById } from '../lib/api'
import { BOARD_CUTOFF_ISO, isOnOrAfterBoardCutoff } from '../lib/boardCutoff'
import { builtInTriggerOptions, isDateTriggerRef } from '../lib/triggerCatalog'
import { hasAnyTriggerConfigured, isTaskTriggered, triggerDisplay } from '../lib/triggerSignal'
import { defaultTaskForm, formFromTask, taskPayloadFromForm, type TaskFormModel } from '../lib/taskForm'
import type { TodoList, TodoTask, TriggerEvent } from '../lib/types'

const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const tasks = ref<TodoTask[]>([])
const lists = ref<TodoList[]>([])
const triggerEvents = ref<TriggerEvent[]>([])
const epicOptions = ref<Array<{ value: string; label: string }>>([])
const epicPriorityByKey = ref(new Map<string, 'P0' | 'P1' | 'P2' | 'P3'>())
const triggerLoading = ref(false)
const epicLoading = ref(false)
const draggingKey = ref('')
const editDialogVisible = ref(false)
const editingTask = ref<TodoTask | null>(null)
const editForm = reactive<TaskFormModel>(defaultTaskForm(''))
const createDialogVisible = ref(false)
const createForm = reactive<TaskFormModel>(defaultTaskForm(''))
const triggerTypeFilter = ref<'all' | 'event-trigger' | 'date-trigger' | 'other-trigger'>('all')

const statuses = computed(() =>
  selectedPool.value === 'waiting-trigger'
    ? ['wait-for-trigger', 'todo', 'doing']
    : ['wait-for-trigger', 'todo', 'doing'],
)

const selectedPool = computed(() => {
  const raw = String(route.params.pool || '')
  if (raw === 'triggered' || raw === 'waiting-trigger') return raw
  return 'triggered'
})

function extension(task: TodoTask) {
  return task.extensions?.find((x) => x.extensionName === 'com.triggertodo.meta')
}

function isTriggeredNow(task: TodoTask) {
  return isTaskTriggered(task, new Map(triggerEvents.value.map((event) => [event.id, event])))
}

function displayPool(task: TodoTask) {
  return hasAnyTriggerConfigured(task) ? 'triggered' : 'waiting-trigger'
}

function defaultStatusForPool() {
  return selectedPool.value === 'waiting-trigger' ? 'wait-for-trigger' : 'todo'
}

function normalizedStatus(task: TodoTask) {
  const raw = (extension(task)?.wfStatus || '').toLowerCase()
  if (selectedPool.value === 'triggered' && hasAnyTriggerConfigured(task) && !isTriggeredNow(task)) {
    return 'wait-for-trigger'
  }
  if (!raw) return defaultStatusForPool()
  if (raw === 'wait-trigger' || raw === 'wait for trigger') return 'wait-for-trigger'
  if (raw === 'todo' || raw === 'doing') return raw
  return defaultStatusForPool()
}

function statusLabel(status: string) {
  if (status === 'wait-for-trigger') return 'Pending Trigger'
  return status
}

function toPriorityP(priority?: string) {
  const value = (priority || '').toLowerCase()
  if (value.includes('p0') || value.includes('highest') || value.includes('critical') || value.includes('blocker')) return 'P0'
  if (value.includes('p1') || value.includes('high') || value.includes('major')) return 'P1'
  if (value.includes('p2') || value.includes('medium') || value.includes('normal')) return 'P2'
  if (value.includes('p3') || value.includes('low') || value.includes('minor')) return 'P3'
  return null
}

function priorityLabel(task: TodoTask) {
  const epicKey = String(extension(task)?.epicKey || '').toUpperCase()
  if (!epicKey) return 'Unknown'
  return epicPriorityByKey.value.get(epicKey) || 'Unknown'
}

function priorityRank(task: TodoTask) {
  const p = priorityLabel(task)
  if (p === 'P0') return 0
  if (p === 'P1') return 1
  if (p === 'P2') return 2
  if (p === 'P3') return 3
  return 9
}

function toTimeMs(value?: string | null) {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}

function triggerLabel(task: TodoTask) {
  return triggerDisplay(task, new Map(triggerEvents.value.map((event) => [event.id, event])))
}

function isCompletedStatus(status?: string) {
  const value = String(status || '').toLowerCase()
  return value.includes('done') || value.includes('closed') || value.includes('resolved') || value.includes('complete')
}

function configuredTriggerType(task: TodoTask) {
  const ref = String(extension(task)?.triggerRef || '').trim().toLowerCase()
  if (ref.startsWith('event:')) return 'event-trigger'
  if (isDateTriggerRef(ref) || task.dueDateTime?.dateTime || task.recurrence?.pattern) return 'date-trigger'
  if (ref) return 'other-trigger'
  return 'none'
}

function matchesTriggerTypeFilter(task: TodoTask) {
  if (selectedPool.value !== 'triggered') return true
  if (triggerTypeFilter.value === 'all') return true
  return configuredTriggerType(task) === triggerTypeFilter.value
}

const indexed = computed(() => {
  const map = new Map<string, TodoTask[]>()
  for (const wfStatus of statuses.value) {
    const rows = tasks.value.filter((task) => {
      if (displayPool(task) !== selectedPool.value) return false
      if (!matchesTriggerTypeFilter(task)) return false
      if (normalizedStatus(task) !== wfStatus) return false
      return true
    })
    rows.sort((a, b) => {
      const rankDiff = priorityRank(a) - priorityRank(b)
      if (rankDiff !== 0) return rankDiff
      return a.title.localeCompare(b.title)
    })
    map.set(
      wfStatus,
      rows,
    )
  }
  return map
})

const waitingTasks = computed(() =>
  tasks.value
    .filter((task) => displayPool(task) === 'waiting-trigger' && matchesTriggerTypeFilter(task))
    .sort((a, b) => {
      const aCreatedMs = toTimeMs(a.createdDateTime)
      const bCreatedMs = toTimeMs(b.createdDateTime)
      if (aCreatedMs !== null && bCreatedMs !== null && aCreatedMs !== bCreatedMs) {
        return bCreatedMs - aCreatedMs
      }
      if (aCreatedMs !== null && bCreatedMs === null) return -1
      if (aCreatedMs === null && bCreatedMs !== null) return 1

      const rankDiff = priorityRank(a) - priorityRank(b)
      if (rankDiff !== 0) return rankDiff
      return a.title.localeCompare(b.title)
    }),
)

async function loadBoard() {
  loading.value = true
  try {
    triggerLoading.value = true
    epicLoading.value = true
    const [data, eventsData, epicsData] = await Promise.all([
      fetchAllTasks(),
      listTriggerEvents(),
      listEpics(),
    ])
    lists.value = data.lists
    triggerEvents.value = eventsData.items
    epicOptions.value = epicsData.items.map((epic) => ({
      value: epic.epic_key,
      label: epic.name || 'Unnamed Epic',
    }))
    const priorityMap = new Map<string, 'P0' | 'P1' | 'P2' | 'P3'>()
    for (const epic of epicsData.items) {
      const p = toPriorityP(epic.priority)
      if (!p) continue
      priorityMap.set(String(epic.epic_key || '').toUpperCase(), p)
    }
    epicPriorityByKey.value = priorityMap
    tasks.value = data.tasks.filter((task) => {
      if (isCompletedStatus(task.status)) return false
      return isOnOrAfterBoardCutoff(task)
    })
    if (!createForm.listId) createForm.listId = data.lists[0]?.id || ''
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load board')
  } finally {
    triggerLoading.value = false
    epicLoading.value = false
    loading.value = false
  }
}

function openCreate() {
  Object.assign(createForm, defaultTaskForm(lists.value[0]?.id || ''))
  createForm.wfStatus = 'wait-for-trigger'
  createDialogVisible.value = true
}

async function submitCreate() {
  const hasTitle = Boolean(createForm.title.trim())
  const resolvedListId = createForm.listId || lists.value[0]?.id || ''
  const hasList = Boolean(resolvedListId)
  if (!hasTitle && !hasList) {
    ElMessage.warning('Title and list are required')
    return
  }
  if (!hasTitle) {
    ElMessage.warning('Title is required')
    return
  }
  if (!hasList) {
    ElMessage.warning('No task list found. Create a list first.')
    return
  }
  if (isDateTriggerRef(createForm.triggerRef) && !createForm.dueAt) {
    ElMessage.warning('Date trigger requires due date')
    return
  }

  saving.value = true
  try {
    createForm.listId = resolvedListId
    createForm.wfStatus = 'wait-for-trigger'
    await createTask(resolvedListId, taskPayloadFromForm(createForm, { includeSource: true }) as never)
    createDialogVisible.value = false
    await loadBoard()
    ElMessage.success('Task created')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to create task')
  } finally {
    saving.value = false
  }
}

function onDragStart(task: TodoTask) {
  draggingKey.value = `${task.listId}:${task.id}`
}

function openEdit(task: TodoTask) {
  editingTask.value = task
  Object.assign(editForm, formFromTask(task))
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editingTask.value) return
  if (!editForm.title.trim()) {
    ElMessage.warning('Title is required')
    return
  }
  if (isDateTriggerRef(editForm.triggerRef) && !editForm.dueAt) {
    ElMessage.warning('Date trigger requires due date')
    return
  }
  saving.value = true
  try {
    await updateTask(editingTask.value.listId, editingTask.value.id, taskPayloadFromForm(editForm))
    editDialogVisible.value = false
    await loadBoard()
    ElMessage.success('Task updated')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update task')
  } finally {
    saving.value = false
  }
}

async function onDrop(targetStatus: string) {
  if (!draggingKey.value) return
  const [listId, taskId] = draggingKey.value.split(':')
  const task = tasks.value.find((item) => item.id === taskId && item.listId === listId)
  draggingKey.value = ''
  if (!task) return
  const currentStatus = normalizedStatus(task)
  if (currentStatus === 'wait-for-trigger' && targetStatus === 'todo') {
    ElMessage.warning('Pending Trigger tasks cannot move to To Do')
    return
  }

  try {
    await updateTaskById(task.id, {
      extensions: {
        wfStatus: targetStatus,
      },
    })

    const extensions = task.extensions || []
    const existing = extensions.find((item) => item.extensionName === 'com.triggertodo.meta')
    if (existing) {
      existing.wfStatus = targetStatus
    } else {
      extensions.push({ extensionName: 'com.triggertodo.meta', wfStatus: targetStatus })
    }
    task.extensions = extensions
    ElMessage.success('Task moved')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to move task')
  }
}

async function markDone(task: TodoTask) {
  try {
    await completeTask(task.listId, task.id)
    await loadBoard()
    ElMessage.success('Task completed')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to complete task')
  }
}

onMounted(loadBoard)
</script>

<template>
  <section class="page-shell">
    <header class="page-head">
      <div>
        <h1>{{ selectedPool === 'triggered' ? 'Trigger Set Board' : 'Trigger Missing Board' }}</h1>
        <p>
          {{
            selectedPool === 'triggered'
              ? `Tasks that already have a trigger configured, updated/created on or after ${BOARD_CUTOFF_ISO.slice(0, 10)}`
              : `Tasks with no trigger configured yet, updated/created on or after ${BOARD_CUTOFF_ISO.slice(0, 10)}`
          }}
        </p>
      </div>
      <div class="actions">
        <el-select
          v-if="selectedPool === 'triggered'"
          v-model="triggerTypeFilter"
          placeholder="Filter trigger type"
          style="width: 190px"
        >
          <el-option label="All triggers" value="all" />
          <el-option label="Event-triggered" value="event-trigger" />
          <el-option label="Date-triggered" value="date-trigger" />
          <el-option label="Other triggers" value="other-trigger" />
        </el-select>
        <el-button v-if="selectedPool === 'waiting-trigger'" type="primary" @click="openCreate">Create Task</el-button>
      </div>
    </header>

    <el-skeleton :loading="loading" animated :rows="6" v-if="loading" />

    <div v-if="selectedPool === 'waiting-trigger'" class="waiting-list">
      <article
        v-for="task in waitingTasks"
        :key="`${task.listId}-${task.id}`"
        class="task-card task-row task-row-clickable waiting-card"
        @click="openEdit(task)"
      >
        <div class="task-main task-main-single">
          <h3 class="task-title-inline">{{ task.title }}</h3>
          <div class="task-inline-meta task-inline-meta-single">
            <el-tag size="small" effect="plain" type="info">{{ task.source }}</el-tag>
            <span v-if="priorityLabel(task) !== 'Unknown'">Priority: {{ priorityLabel(task) }}</span>
            <span>Trigger: {{ triggerLabel(task) }}</span>
          </div>
        </div>
        <div class="task-actions task-actions-inline">
          <el-button size="small" type="success" @click.stop="markDone(task)">Done</el-button>
        </div>
      </article>
      <el-empty v-if="!waitingTasks.length" description="No tasks missing trigger setup" />
    </div>

    <div v-else class="board-grid board-grid-status">
      <article class="board-col" v-for="status in statuses" :key="status">
        <h2>{{ statusLabel(status) }}</h2>
        <div
          class="drop-zone drop-zone-fill"
          @dragover.prevent
          @drop.prevent="onDrop(status)"
        >
          <header>
            <span>{{ statusLabel(status) }}</span>
            <el-tag size="small" effect="plain">{{ indexed.get(status)?.length || 0 }}</el-tag>
          </header>
          <div
            v-for="task in indexed.get(status) || []"
            :key="`${task.listId}-${task.id}`"
            class="kanban-card"
            draggable="true"
            @click="openEdit(task)"
            @dragstart="onDragStart(task)"
          >
            <h3>{{ task.title }}</h3>
            <div class="kanban-meta">
              <span class="meta-chip">Source: {{ task.source }}</span>
              <span v-if="priorityLabel(task) !== 'Unknown'" class="meta-chip">Priority: {{ priorityLabel(task) }}</span>
              <span class="meta-chip">Trigger: {{ triggerLabel(task) }}</span>
            </div>
            <p v-if="task.body?.content?.trim()" class="kanban-note">{{ task.body.content }}</p>
            <div v-if="status === 'doing'" class="kanban-actions">
              <el-button size="small" type="success" @click.stop="markDone(task)">Done</el-button>
            </div>
          </div>
        </div>
      </article>
    </div>

    <TaskEditDialog
      v-model="createDialogVisible"
      :model="createForm"
      :lists="lists"
      :readonly-list="false"
      :hide-workflow-status="true"
      :saving="saving"
      title="Create Task"
      save-text="Create"
      :trigger-options="[
        ...builtInTriggerOptions(),
        ...triggerEvents.map((event) => ({ value: `event:${event.id}`, label: `event-trigger: ${event.name}${event.is_active ? ' (occurred)' : ''}` })),
      ]"
      :trigger-loading="triggerLoading"
      :epic-options="epicOptions"
      :epic-loading="epicLoading"
      @save="submitCreate"
    />

    <TaskEditDialog
      v-model="editDialogVisible"
      :model="editForm"
      :lists="lists"
      :readonly-list="true"
      :hide-workflow-status="true"
      :saving="saving"
      :trigger-options="[
        ...builtInTriggerOptions(),
        ...triggerEvents.map((event) => ({ value: `event:${event.id}`, label: `event-trigger: ${event.name}${event.is_active ? ' (occurred)' : ''}` })),
      ]"
      :trigger-loading="triggerLoading"
      :epic-options="epicOptions"
      :epic-loading="epicLoading"
      @save="submitEdit"
    />
  </section>
</template>
