<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import TaskForm from '../components/TaskForm.vue'
import {
  completeTask,
  createTask,
  deleteTask,
  listEpics,
  fetchAllTasks,
  listTriggerEvents,
  updateTask,
} from '../lib/api'
import { BOARD_CUTOFF_ISO } from '../lib/boardCutoff'
import { isTaskTriggered } from '../lib/triggerSignal'
import { builtInTriggerOptions, isDateTriggerRef } from '../lib/triggerCatalog'
import { defaultTaskForm, formFromTask, taskPayloadFromForm, type TaskFormModel } from '../lib/taskForm'
import type { TodoList, TodoTask, TriggerEvent } from '../lib/types'

const loading = ref(false)
const saving = ref(false)
const tasks = ref<TodoTask[]>([])
const lists = ref<TodoList[]>([])
const triggerEvents = ref<TriggerEvent[]>([])
const triggerLoading = ref(false)
const search = ref('')

const createDialogVisible = ref(false)
const editDialogVisible = ref(false)
const waitingExpanded = ref(false)
const waitingPage = ref(1)
const waitingPageSize = 8
const createForm = reactive<TaskFormModel>(defaultTaskForm(''))
const editForm = reactive<TaskFormModel>(defaultTaskForm(''))
const editingTask = ref<TodoTask | null>(null)
const epicPriorityByKey = ref(new Map<string, 'P0' | 'P1' | 'P2' | 'P3'>())
const epicOptions = ref<Array<{ value: string; label: string }>>([])
const epicLoading = ref(false)
const eventsById = computed(() => new Map<number, TriggerEvent>(triggerEvents.value.map((event) => [event.id, event])))
const triggerOptions = computed(() =>
  [
    ...builtInTriggerOptions(),
    ...triggerEvents.value.map((event) => ({
      value: `event:${event.id}`,
      label: `event-trigger: ${event.name}${event.is_active ? ' (occurred)' : ''}`,
      disabled: false,
    })),
  ],
)

const filteredTasks = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  let rows = tasks.value.filter((task) => task.status !== 'completed')
  if (!keyword) return rows
  return rows.filter((task) => {
    const ext = task.extensions?.find((x) => x.extensionName === 'com.triggertodo.meta')
    const haystack = `${task.title} ${task.body?.content || ''} ${ext?.wfStatus || ''}`.toLowerCase()
    return haystack.includes(keyword)
  })
})

function extension(task: TodoTask) {
  return task.extensions?.find((item) => item.extensionName === 'com.triggertodo.meta') || {}
}

function hasTrigger(task: TodoTask) {
  return isTaskTriggered(task, eventsById.value)
}

function triggerLabel(task: TodoTask) {
  const ext = extension(task)
  if (task.dueDateTime?.dateTime) {
    const dt = new Date(task.dueDateTime.dateTime)
    if (!Number.isNaN(dt.getTime())) return `date ${dt.toLocaleString()}`
    return `date ${task.dueDateTime.dateTime}`
  }
  const recurrenceType = String(task.recurrence?.pattern?.['type'] || '').toLowerCase()
  if (recurrenceType) {
    const interval = Number(task.recurrence?.pattern?.['interval'] || 1)
    const unit = recurrenceType === 'daily' ? 'day(s)' : recurrenceType === 'weekly' ? 'week(s)' : 'month(s)'
    return `recurrence every ${interval} ${unit}`
  }
  if (ext.triggerRef) return `rule #${ext.triggerRef}`
  return 'none'
}

function toPriorityP(priority?: string) {
  const value = (priority || '').toLowerCase()
  if (value.includes('p0') || value.includes('highest') || value.includes('critical') || value.includes('blocker')) return 'P0'
  if (value.includes('p1') || value.includes('high') || value.includes('major')) return 'P1'
  if (value.includes('p2') || value.includes('medium') || value.includes('normal')) return 'P2'
  if (value.includes('p3') || value.includes('low') || value.includes('minor')) return 'P3'
  return null
}

function extractPriorityFromSummary(summary?: string) {
  const text = summary || ''
  const match = text.match(/\[(P[0-3])\]/i)
  const token = match?.[1]
  if (!token) return null
  const normalized = token.toUpperCase()
  if (normalized === 'P0' || normalized === 'P1' || normalized === 'P2' || normalized === 'P3') return normalized
  return null
}

function priorityLabel(task: TodoTask) {
  const epicKey = String(extension(task).epicKey || '').toUpperCase()
  if (!epicKey) return 'Unknown'
  return epicPriorityByKey.value.get(epicKey) || 'Unknown'
}

async function loadEpicPriorities() {
  try {
    const response = await listEpics()
    const map = new Map<string, 'P0' | 'P1' | 'P2' | 'P3'>()
    epicOptions.value = response.items.map((epic) => ({
      value: epic.epic_key,
      label: epic.name || epic.epic_key,
    }))
    for (const epic of response.items || []) {
      const fromSummary = extractPriorityFromSummary(epic.name)
      const fromPriority = toPriorityP(epic.priority)
      const priority = (fromSummary || fromPriority) as 'P0' | 'P1' | 'P2' | 'P3' | null
      if (!priority) continue
      if (!epic.epic_key) continue
      map.set(epic.epic_key.toUpperCase(), priority)
    }
    epicPriorityByKey.value = map
  } catch {
    // Keep priority labels as Unknown when Jira lookup fails.
    epicPriorityByKey.value = new Map()
    epicOptions.value = []
  }
}

const groupedTasks = computed(() => {
  const triggered = filteredTasks.value.filter((task) => hasTrigger(task))
  const waiting = filteredTasks.value.filter((task) => !hasTrigger(task))
  return { triggered, waiting }
})

const waitingPagedTasks = computed(() => {
  const start = (waitingPage.value - 1) * waitingPageSize
  return groupedTasks.value.waiting.slice(start, start + waitingPageSize)
})

watch(
  () => groupedTasks.value.waiting.length,
  () => {
    waitingPage.value = 1
  },
)

function resetCreateForm() {
  Object.assign(createForm, defaultTaskForm(lists.value[0]?.id || ''))
}

async function loadData() {
  loading.value = true
  try {
    epicLoading.value = true
    await loadEpicPriorities()
    triggerLoading.value = true
    const [data, eventsData] = await Promise.all([fetchAllTasks(), listTriggerEvents()])
    tasks.value = data.tasks
    lists.value = data.lists
    triggerEvents.value = eventsData.items
    if (!createForm.listId) createForm.listId = data.lists[0]?.id || ''
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load tasks')
  } finally {
    epicLoading.value = false
    triggerLoading.value = false
    loading.value = false
  }
}

function openCreate() {
  resetCreateForm()
  createDialogVisible.value = true
}

function openEdit(task: TodoTask) {
  editingTask.value = task
  Object.assign(editForm, formFromTask(task))
  editDialogVisible.value = true
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
    await createTask(resolvedListId, taskPayloadFromForm(createForm, { includeSource: true }) as never)
    createDialogVisible.value = false
    await loadData()
    ElMessage.success('Task created')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to create task')
  } finally {
    saving.value = false
  }
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
    await loadData()
    ElMessage.success('Task updated')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update task')
  } finally {
    saving.value = false
  }
}

async function markComplete(task: TodoTask) {
  try {
    await completeTask(task.listId, task.id)
    await loadData()
    ElMessage.success('Marked complete')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to complete task')
  }
}

async function removeTask(task: TodoTask) {
  try {
    await deleteTask(task.listId, task.id)
    tasks.value = tasks.value.filter((item) => item.id !== task.id)
    ElMessage.success('Task deleted')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to delete task')
  }
}

onMounted(loadData)
</script>

<template>
  <section class="page-shell">
    <header class="page-head">
      <div>
        <h1>Today</h1>
        <p>{{ filteredTasks.length }} open task(s), updated/created on or after {{ BOARD_CUTOFF_ISO.slice(0, 10) }}</p>
      </div>
      <div class="actions">
        <el-input v-model="search" placeholder="Search title/notes/status" clearable class="search" />
        <el-button type="primary" @click="openCreate">New Task</el-button>
      </div>
    </header>

    <el-skeleton :loading="loading" animated :rows="6" v-if="loading" />

    <el-empty v-else-if="!filteredTasks.length" description="No tasks for today" />

    <div v-else class="today-sections">
      <section>
        <h2 class="pool-title">Triggered Tasks</h2>
        <el-empty v-if="!groupedTasks.triggered.length" description="No tasks with trigger set" />
        <div v-else class="waiting-list">
          <article class="task-card task-row task-row-clickable" v-for="task in groupedTasks.triggered" :key="`${task.listId}-${task.id}`" @click="openEdit(task)">
            <div class="task-main task-main-single">
              <h3 class="task-title-inline">{{ task.title }}</h3>
              <div class="task-inline-meta task-inline-meta-single">
                <el-tag size="small" effect="plain" type="info">{{ task.source }}</el-tag>
                <el-tag v-if="extension(task).wfStatus" size="small" effect="plain">{{ extension(task).wfStatus }}</el-tag>
                <span>Priority: {{ priorityLabel(task) }}</span>
                <span>Trigger: {{ triggerLabel(task) }}</span>
              </div>
            </div>
            <div class="task-actions task-actions-inline">
              <el-button size="small" type="success" @click.stop="markComplete(task)">Complete</el-button>
              <el-popconfirm title="Delete this task?" @confirm="removeTask(task)">
                <template #reference>
                  <el-button size="small" type="danger" plain @click.stop>Delete</el-button>
                </template>
              </el-popconfirm>
            </div>
          </article>
        </div>
      </section>

      <section>
        <div class="section-head">
          <h2 class="pool-title">Waiting for Trigger</h2>
          <el-button text size="small" @click="waitingExpanded = !waitingExpanded">
            {{ waitingExpanded ? 'Collapse' : `Expand (${groupedTasks.waiting.length})` }}
          </el-button>
        </div>
        <p v-if="!waitingExpanded" class="collapsed-hint">Hidden until expanded</p>
        <el-empty v-else-if="!groupedTasks.waiting.length" description="No tasks waiting for trigger" />
        <div v-else class="waiting-list">
          <article class="task-card task-row task-row-clickable" v-for="task in waitingPagedTasks" :key="`${task.listId}-${task.id}`" @click="openEdit(task)">
            <div class="task-main task-main-single">
              <h3 class="task-title-inline">{{ task.title }}</h3>
              <div class="task-inline-meta task-inline-meta-single">
                <el-tag size="small" effect="plain" type="info">{{ task.source }}</el-tag>
                <el-tag v-if="extension(task).wfStatus" size="small" effect="plain">{{ extension(task).wfStatus }}</el-tag>
                <span>Priority: {{ priorityLabel(task) }}</span>
                <span>Trigger: {{ triggerLabel(task) }}</span>
              </div>
            </div>
            <div class="task-actions task-actions-inline">
              <el-button size="small" type="success" @click.stop="markComplete(task)">Complete</el-button>
              <el-popconfirm title="Delete this task?" @confirm="removeTask(task)">
                <template #reference>
                  <el-button size="small" type="danger" plain @click.stop>Delete</el-button>
                </template>
              </el-popconfirm>
            </div>
          </article>
          <el-pagination
            v-if="groupedTasks.waiting.length > waitingPageSize"
            v-model:current-page="waitingPage"
            :page-size="waitingPageSize"
            layout="prev, pager, next"
            :total="groupedTasks.waiting.length"
            class="waiting-pagination"
          />
        </div>
      </section>
    </div>

    <el-dialog v-model="createDialogVisible" title="Create Task" width="760" class="task-dialog">
      <TaskForm
        :model="createForm"
        :lists="lists"
        :trigger-options="triggerOptions"
        :trigger-loading="triggerLoading"
        :epic-options="epicOptions"
        :epic-loading="epicLoading"
      />
      <template #footer>
        <el-button @click="createDialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">Create</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editDialogVisible" title="Edit Task" width="760" class="task-dialog">
      <TaskForm
        :model="editForm"
        :lists="lists"
        :readonly-list="true"
        :trigger-options="triggerOptions"
        :trigger-loading="triggerLoading"
        :epic-options="epicOptions"
        :epic-loading="epicLoading"
      />
      <template #footer>
        <el-button @click="editDialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">Save</el-button>
      </template>
    </el-dialog>
  </section>
</template>
