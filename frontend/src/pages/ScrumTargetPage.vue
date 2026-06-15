<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  completeScrum,
  createScrum,
  fetchAllTasks,
  getActiveScrum,
  listEpics,
  listScrums,
  listTriggerEvents,
  updateScrum,
  updateScrumItemStatus,
} from '../lib/api'
import { hasAnyTriggerConfigured, isTaskTriggered, triggerDisplay } from '../lib/triggerSignal'
import type { TodoTask, TriggerEvent, TriggerScrum, TriggerScrumItem } from '../lib/types'

type ScrumStatus = 'todo' | 'doing' | 'done'
type PriorityTag = 'P0' | 'P1' | 'P2' | 'P3'

const FIBONACCI_POINTS = [1, 2, 3, 5, 8, 13, 21, 34] as const
const columns: Array<{ status: ScrumStatus; label: string }> = [
  { status: 'todo', label: 'TODO' },
  { status: 'doing', label: 'DOING' },
  { status: 'done', label: 'DONE' },
]

const loading = ref(false)
const saving = ref(false)
const movingItemId = ref<number | null>(null)
const draggingItemId = ref<number | null>(null)
const tasks = ref<TodoTask[]>([])
const triggerEvents = ref<TriggerEvent[]>([])
const activeScrum = ref<TriggerScrum | null>(null)
const scrumHistory = ref<TriggerScrum[]>([])
const selectedTaskKeys = ref<string[]>([])
const pointOverrides = ref<Record<string, number>>({})
const epicPriorityByKey = ref(new Map<string, PriorityTag>())

const today = new Date()
const twoWeeks = new Date(today)
twoWeeks.setDate(today.getDate() + 13)

const draft = reactive({
  name: 'Current Sprint',
  goal: '',
  startDate: today.toISOString().slice(0, 10),
  endDate: twoWeeks.toISOString().slice(0, 10),
})

function taskKey(task: TodoTask) {
  return `${task.listId}:${task.id}`
}

function itemKey(item: TriggerScrumItem) {
  return `${item.list_id}:${item.task_id}`
}

function extension(task?: TodoTask) {
  return task?.extensions?.find((item) => item.extensionName === 'com.triggertodo.meta')
}

function eventsById() {
  return new Map(triggerEvents.value.map((event) => [event.id, event]))
}

function isCompletedStatus(status?: string | null) {
  const value = String(status || '').toLowerCase()
  return value.includes('done') || value.includes('closed') || value.includes('resolved') || value.includes('complete')
}

function normalizeWorkflowStatus(task: TodoTask): ScrumStatus {
  const value = String(extension(task)?.wfStatus || '').toLowerCase()
  return value === 'doing' ? 'doing' : 'todo'
}

function normalizePriorityTag(priority?: string | null): PriorityTag {
  const value = String(priority || '').toLowerCase()
  if (value.includes('p0') || value.includes('highest') || value.includes('critical') || value.includes('blocker')) return 'P0'
  if (value.includes('p1') || value.includes('high') || value.includes('major')) return 'P1'
  if (value.includes('p2') || value.includes('medium') || value.includes('normal')) return 'P2'
  if (value.includes('p3') || value.includes('low') || value.includes('minor')) return 'P3'
  return 'P2'
}

function priorityRank(priorityTag: PriorityTag | 'Unknown') {
  if (priorityTag === 'P0') return 0
  if (priorityTag === 'P1') return 1
  if (priorityTag === 'P2') return 2
  if (priorityTag === 'P3') return 3
  return 9
}

function priorityTagType(priorityTag: PriorityTag | 'Unknown') {
  if (priorityTag === 'P0') return 'danger'
  if (priorityTag === 'P1') return 'warning'
  if (priorityTag === 'P2') return 'success'
  return 'info'
}

function priorityLabel(task?: TodoTask): PriorityTag | 'Unknown' {
  const epicKey = String(extension(task)?.epicKey || '').toUpperCase()
  if (!epicKey) return 'Unknown'
  return epicPriorityByKey.value.get(epicKey) || 'Unknown'
}

function defaultPointsFor(task: TodoTask) {
  const priority = priorityLabel(task)
  if (priority === 'P0') return 8
  if (priority === 'P1') return 5
  if (priority === 'P2') return 3
  if (task.importance === 'high') return 5
  if (task.importance === 'low') return 2
  return 3
}

function pointsFor(task: TodoTask) {
  return pointOverrides.value[taskKey(task)] || defaultPointsFor(task)
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const at = new Date(value)
  return Number.isNaN(at.getTime()) ? '' : at.toLocaleDateString()
}

const taskByKey = computed(() => new Map(tasks.value.map((task) => [taskKey(task), task])))
const activeItemKeys = computed(() => new Set((activeScrum.value?.items || []).map(itemKey)))

const candidateTasks = computed(() => {
  const eventMap = eventsById()
  return tasks.value
    .filter((task) => !isCompletedStatus(task.status))
    .filter((task) => hasAnyTriggerConfigured(task) && isTaskTriggered(task, eventMap))
    .filter((task) => !activeItemKeys.value.has(taskKey(task)))
    .sort((a, b) => {
      const priorityDiff = priorityRank(priorityLabel(a)) - priorityRank(priorityLabel(b))
      if (priorityDiff !== 0) return priorityDiff
      return a.title.localeCompare(b.title)
    })
})

const selectedTasks = computed(() => candidateTasks.value.filter((task) => selectedTaskKeys.value.includes(taskKey(task))))
const selectedPoints = computed(() => selectedTasks.value.reduce((sum, task) => sum + pointsFor(task), 0))
const sprintPoints = computed(() => activeScrum.value?.summary.points || 0)
const donePoints = computed(() => activeScrum.value?.summary.done_points || 0)
const sprintProgress = computed(() => (sprintPoints.value ? Math.round((donePoints.value / sprintPoints.value) * 100) : 0))
const completedScrums = computed(() =>
  scrumHistory.value
    .filter((scrum) => scrum.status === 'completed')
    .sort((a, b) => {
      const aTime = Date.parse(a.completed_at || a.updated_at || '')
      const bTime = Date.parse(b.completed_at || b.updated_at || '')
      return (Number.isNaN(bTime) ? 0 : bTime) - (Number.isNaN(aTime) ? 0 : aTime)
    })
    .slice(0, 6),
)
const storyPointHistory = computed(() =>
  [...completedScrums.value]
    .reverse()
    .map((scrum) => ({
      id: scrum.id,
      name: scrum.name,
      committed: scrum.summary.points,
      completed: scrum.summary.done_points,
    })),
)
const velocityAverage = computed(() => {
  if (!completedScrums.value.length) return 0
  const done = completedScrums.value.reduce((sum, scrum) => sum + scrum.summary.done_points, 0)
  return Math.round(done / completedScrums.value.length)
})
const suggestedLow = computed(() => (velocityAverage.value ? Math.max(1, Math.floor(velocityAverage.value * 0.8)) : 0))
const suggestedHigh = computed(() => (velocityAverage.value ? Math.ceil(velocityAverage.value * 1.2) : 0))
const historyChartMax = computed(() =>
  Math.max(
    1,
    selectedPoints.value,
    velocityAverage.value,
    ...storyPointHistory.value.flatMap((item) => [item.committed, item.completed]),
  ),
)
const historyAxisTicks = computed(() => {
  const max = historyChartMax.value
  const mid = Math.round(max / 2)
  return [max, mid, 0]
})
const historyChartHeight = 178
const historyChartLabelOffset = 52
const suggestedBandStyle = computed(() => {
  if (!velocityAverage.value) return {}
  const high = Math.min(historyChartMax.value, suggestedHigh.value)
  const low = Math.min(historyChartMax.value, suggestedLow.value)
  return {
    bottom: `${historyChartLabelOffset + (low / historyChartMax.value) * historyChartHeight}px`,
    height: `${Math.max(2, ((high - low) / historyChartMax.value) * historyChartHeight)}px`,
  }
})
const averageLineStyle = computed(() => {
  if (!velocityAverage.value) return {}
  return {
    bottom: `${
      historyChartLabelOffset +
      (Math.min(historyChartMax.value, velocityAverage.value) / historyChartMax.value) * historyChartHeight
    }px`,
  }
})
const planningProgress = computed(() =>
  velocityAverage.value ? Math.min(120, Math.round((selectedPoints.value / velocityAverage.value) * 100)) : 0,
)
const selectionGuide = computed(() => {
  if (!velocityAverage.value) return 'Complete a scrum to build a velocity history.'
  if (selectedPoints.value < suggestedLow.value) return 'Below recent velocity; add more triggered work if available.'
  if (selectedPoints.value > suggestedHigh.value) return 'Above recent velocity; consider removing or splitting work.'
  return 'Close to recent velocity.'
})

function boardColumnItems(status: ScrumStatus) {
  return (activeScrum.value?.items || []).filter((item) => item.status === status)
}

function boardTask(item: TriggerScrumItem) {
  return taskByKey.value.get(itemKey(item))
}

function boardTitle(item: TriggerScrumItem) {
  return boardTask(item)?.title || item.task?.title || item.task_id
}

function boardPriority(item: TriggerScrumItem): PriorityTag | 'Unknown' {
  const task = boardTask(item)
  if (task) return priorityLabel(task)
  return 'Unknown'
}

function boardTrigger(item: TriggerScrumItem) {
  const task = boardTask(item)
  if (task) return triggerDisplay(task, eventsById())
  return item.task?.trigger_ref || 'Missing task'
}

function boardEpic(item: TriggerScrumItem) {
  const task = boardTask(item)
  return String(extension(task)?.epicKey || item.task?.epic_key || 'No epic')
}

function isSelected(task: TodoTask) {
  return selectedTaskKeys.value.includes(taskKey(task))
}

function setSelected(task: TodoTask, selected: boolean) {
  const key = taskKey(task)
  if (selected && !selectedTaskKeys.value.includes(key)) {
    selectedTaskKeys.value = [...selectedTaskKeys.value, key]
    return
  }
  if (!selected) selectedTaskKeys.value = selectedTaskKeys.value.filter((item) => item !== key)
}

function setPoints(task: TodoTask, value: number) {
  pointOverrides.value = { ...pointOverrides.value, [taskKey(task)]: value }
}

function selectAllTriggered() {
  selectedTaskKeys.value = candidateTasks.value.map(taskKey)
}

function clearSelected() {
  selectedTaskKeys.value = []
}

function applyScrumToDraft(scrum: TriggerScrum) {
  draft.name = scrum.name
  draft.goal = scrum.goal || ''
  draft.startDate = scrum.start_date || draft.startDate
  draft.endDate = scrum.end_date || draft.endDate
}

function selectedPayload() {
  return selectedTasks.value.map((task) => ({
    list_id: task.listId,
    task_id: task.id,
    points: pointsFor(task),
    status: normalizeWorkflowStatus(task),
  }))
}

async function createOrUpdateScrum() {
  if (!draft.name.trim()) {
    ElMessage.warning('Scrum name is required')
    return
  }
  if (!draft.startDate || !draft.endDate) {
    ElMessage.warning('Start and end dates are required')
    return
  }
  if (!selectedTasks.value.length && !activeScrum.value) {
    ElMessage.warning('Select at least one triggered task')
    return
  }

  saving.value = true
  try {
    if (activeScrum.value) {
      activeScrum.value = await updateScrum(activeScrum.value.id, {
        name: draft.name.trim(),
        goal: draft.goal || null,
        start_date: draft.startDate,
        end_date: draft.endDate,
        target_points: activeScrum.value.summary.points + selectedPoints.value,
        items: [
          ...activeScrum.value.items.map((item) => ({
            list_id: item.list_id,
            task_id: item.task_id,
            points: item.points,
            status: item.status,
          })),
          ...selectedPayload(),
        ],
      })
      ElMessage.success('Scrum updated')
    } else {
      activeScrum.value = await createScrum({
        name: draft.name.trim(),
        goal: draft.goal || null,
        start_date: draft.startDate,
        end_date: draft.endDate,
        target_points: selectedPoints.value,
        status: 'active',
        items: selectedPayload(),
      })
      ElMessage.success('Scrum started')
    }
    selectedTaskKeys.value = []
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to save scrum')
  } finally {
    saving.value = false
  }
}

async function moveItem(item: TriggerScrumItem, status: ScrumStatus) {
  if (!activeScrum.value || item.status === status) return
  movingItemId.value = item.id
  try {
    activeScrum.value = await updateScrumItemStatus(activeScrum.value.id, item.id, status)
    await loadScrum()
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to move task')
  } finally {
    movingItemId.value = null
  }
}

function onDragStart(item: TriggerScrumItem, event: DragEvent) {
  draggingItemId.value = item.id
  event.dataTransfer?.setData('text/plain', String(item.id))
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onMouseDragStart(item: TriggerScrumItem, event: MouseEvent) {
  event.preventDefault()
  draggingItemId.value = item.id
}

function onDragEnd() {
  draggingItemId.value = null
}

async function onDrop(status: ScrumStatus, event: DragEvent) {
  event.preventDefault()
  const rawId = event.dataTransfer?.getData('text/plain') || String(draggingItemId.value || '')
  const itemId = Number(rawId)
  const item = activeScrum.value?.items.find((candidate) => candidate.id === itemId)
  draggingItemId.value = null
  if (!item) return
  await moveItem(item, status)
}

async function onMouseDrop(status: ScrumStatus) {
  const item = activeScrum.value?.items.find((candidate) => candidate.id === draggingItemId.value)
  draggingItemId.value = null
  if (!item) return
  await moveItem(item, status)
}

async function completeActiveScrum() {
  if (!activeScrum.value) return
  saving.value = true
  try {
    activeScrum.value = await completeScrum(activeScrum.value.id)
    ElMessage.success('Scrum completed')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to complete scrum')
  } finally {
    saving.value = false
  }
}

async function loadScrum() {
  loading.value = true
  try {
    const [taskData, epicsData, eventsData, activeData, historyData] = await Promise.all([
      fetchAllTasks(),
      listEpics(),
      listTriggerEvents(),
      getActiveScrum(),
      listScrums(),
    ])
    tasks.value = taskData.tasks
    triggerEvents.value = eventsData.items
    activeScrum.value = activeData.item
    scrumHistory.value = historyData.items
    if (activeData.item) applyScrumToDraft(activeData.item)

    const priorityMap = new Map<string, PriorityTag>()
    for (const epic of epicsData.items) {
      priorityMap.set(String(epic.epic_key || '').toUpperCase(), normalizePriorityTag(epic.priority))
    }
    epicPriorityByKey.value = priorityMap
    selectedTaskKeys.value = selectedTaskKeys.value.filter((key) => candidateTasks.value.some((task) => taskKey(task) === key))
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load scrum')
  } finally {
    loading.value = false
  }
}

onMounted(loadScrum)
</script>

<template>
  <section class="page-shell scrum-page">
    <header class="page-head">
      <div>
        <h1>{{ activeScrum ? activeScrum.name : 'Create Scrum' }}</h1>
        <p>
          {{ activeScrum ? `${activeScrum.start_date || '-'} to ${activeScrum.end_date || '-'}` : `${candidateTasks.length} triggered task(s)` }}
        </p>
      </div>
      <div class="actions">
        <el-button @click="loadScrum" :loading="loading">Refresh</el-button>
      </div>
    </header>

    <template v-if="activeScrum && activeScrum.status === 'active'">
      <section class="scrum-active-summary">
        <div class="scrum-kpis">
          <article class="scrum-kpi scrum-kpi-target">
            <span class="metric-label">Committed</span>
            <strong class="metric-value">{{ sprintPoints }}</strong>
          </article>
          <article class="scrum-kpi scrum-kpi-planned">
            <span class="metric-label">Done</span>
            <strong class="metric-value">{{ donePoints }}</strong>
          </article>
          <article class="scrum-kpi scrum-kpi-remaining">
            <span class="metric-label">Remaining</span>
            <strong class="metric-value">{{ sprintPoints - donePoints }}</strong>
          </article>
          <article class="scrum-kpi scrum-kpi-guide">
            <span class="metric-label">Tasks</span>
            <strong class="metric-value">{{ activeScrum.summary.items }}</strong>
          </article>
        </div>

        <div class="scrum-progress">
          <div class="scrum-progress-head">
            <strong>{{ activeScrum.goal || activeScrum.name }}</strong>
            <span>{{ donePoints }} / {{ sprintPoints }} points done</span>
          </div>
          <el-progress :percentage="sprintProgress" status="success" :stroke-width="12" />
        </div>
      </section>

      <section class="scrum-board-section">
      <div class="scrum-board-head">
        <strong>{{ activeScrum.name }}</strong>
        <div class="scrum-button-row">
          <el-tag effect="dark" type="success">Active</el-tag>
          <el-button type="danger" plain :loading="saving" @click="completeActiveScrum">Complete Scrum</el-button>
        </div>
      </div>
      <div class="scrum-board-grid">
        <article
          v-for="column in columns"
          :key="column.status"
          class="scrum-board-col"
          @dragover.prevent
          @drop="onDrop(column.status, $event)"
          @mouseup="onMouseDrop(column.status)"
        >
          <header>
            <span>{{ column.label }}</span>
            <el-tag size="small" effect="plain">{{ activeScrum.summary.count_by_status[column.status] }}</el-tag>
          </header>
          <div class="scrum-board-stack">
            <article
              v-for="item in boardColumnItems(column.status)"
              :key="item.id"
              class="scrum-task-card"
              :class="{ 'is-dragging': draggingItemId === item.id }"
              draggable="true"
              @dragstart="onDragStart(item, $event)"
              @dragend="onDragEnd"
              @mousedown="onMouseDragStart(item, $event)"
            >
              <div class="scrum-task-title">
                <strong>{{ boardTitle(item) }}</strong>
                <el-tag size="small" effect="dark" :type="priorityTagType(boardPriority(item))">
                  {{ boardPriority(item) }}
                </el-tag>
              </div>
              <div class="scrum-task-meta">
                <span>{{ item.points }} pts</span>
                <span>{{ boardEpic(item) }}</span>
                <span>{{ boardTrigger(item) }}</span>
                <span v-if="item.added_after_start">added after start</span>
              </div>
            </article>
            <el-empty v-if="!boardColumnItems(column.status).length" description="No tasks" :image-size="64" />
          </div>
        </article>
      </div>
    </section>
    </template>

    <template v-else>
      <section class="scrum-target-panel">
        <div class="scrum-controls">
          <el-form label-position="top" @submit.prevent>
            <div class="scrum-control-grid">
              <el-form-item label="Scrum">
                <el-input v-model="draft.name" placeholder="Current Sprint" clearable />
              </el-form-item>
              <el-form-item label="Start">
                <el-input v-model="draft.startDate" type="date" />
              </el-form-item>
              <el-form-item label="End">
                <el-input v-model="draft.endDate" type="date" />
              </el-form-item>
              <el-form-item label="Goal">
                <el-input v-model="draft.goal" placeholder="Sprint goal" clearable />
              </el-form-item>
              <el-form-item label="Tasks">
                <div class="scrum-button-row">
                  <el-button @click="selectAllTriggered">Select Triggered</el-button>
                  <el-button @click="clearSelected">Clear</el-button>
                  <el-button type="primary" :loading="saving" @click="createOrUpdateScrum">Start Scrum</el-button>
                </div>
              </el-form-item>
            </div>
          </el-form>
        </div>

        <div class="scrum-kpis">
          <article class="scrum-kpi scrum-kpi-target">
            <span class="metric-label">Recent Velocity</span>
            <strong class="metric-value">{{ velocityAverage || '-' }}</strong>
          </article>
          <article class="scrum-kpi scrum-kpi-planned">
            <span class="metric-label">Committed</span>
            <strong class="metric-value">{{ selectedPoints }}</strong>
          </article>
          <article class="scrum-kpi scrum-kpi-remaining">
            <span class="metric-label">Suggested</span>
            <strong class="metric-value">{{ velocityAverage ? `${suggestedLow}-${suggestedHigh}` : '-' }}</strong>
          </article>
          <article class="scrum-kpi scrum-kpi-guide">
            <span class="metric-label">Tasks</span>
            <strong class="metric-value">{{ selectedTasks.length }}</strong>
          </article>
        </div>

        <div class="scrum-progress">
          <div class="scrum-progress-head">
            <strong>{{ draft.name || 'Current Sprint' }}</strong>
            <span>{{ selectedPoints }} story point(s) selected</span>
          </div>
          <el-progress
            :percentage="planningProgress"
            :status="velocityAverage && selectedPoints > suggestedHigh ? 'exception' : 'success'"
            :stroke-width="12"
          />
          <p>{{ selectionGuide }}</p>
        </div>
      </section>

      <section class="scrum-history-panel">
        <div class="scrum-history-head">
          <strong>Story point history</strong>
          <span>{{ completedScrums.length ? 'Completed vs committed points' : 'No completed scrums yet' }}</span>
        </div>
        <div v-if="storyPointHistory.length" class="scrum-history-chart">
          <div class="scrum-history-legend">
            <span><i class="legend-swatch legend-committed"></i>Committed</span>
            <span><i class="legend-swatch legend-completed"></i>Completed</span>
          </div>
          <div class="scrum-velocity-chart">
            <div class="scrum-velocity-axis">
              <span v-for="tick in historyAxisTicks" :key="tick">{{ tick }}</span>
            </div>
            <div class="scrum-velocity-plot">
              <div class="scrum-velocity-grid">
                <span v-for="tick in historyAxisTicks" :key="tick"></span>
              </div>
              <div
                v-if="velocityAverage"
                class="scrum-velocity-band"
                :style="suggestedBandStyle"
              >
                <span>{{ suggestedLow }}-{{ suggestedHigh }} recommended</span>
              </div>
              <div
                v-if="velocityAverage"
                class="scrum-velocity-average"
                :style="averageLineStyle"
              >
                <span>avg {{ velocityAverage }}</span>
              </div>
              <article v-for="item in storyPointHistory" :key="item.id" class="scrum-velocity-sprint">
                <div
                  class="scrum-velocity-stacked-bar"
                  :style="{ height: `${Math.max(3, (Math.max(item.committed, item.completed) / historyChartMax) * 100)}%` }"
                  :title="`${item.completed} completed / ${item.committed} committed`"
                >
                  <span class="scrum-velocity-total">{{ item.committed }}</span>
                  <div
                    class="scrum-velocity-segment scrum-velocity-segment-remaining"
                    :style="{ height: `${Math.max(0, ((Math.max(item.committed, item.completed) - item.completed) / Math.max(1, Math.max(item.committed, item.completed))) * 100)}%` }"
                  ></div>
                  <div
                    class="scrum-velocity-segment scrum-velocity-segment-completed"
                    :style="{ height: `${Math.max(4, (item.completed / Math.max(1, Math.max(item.committed, item.completed))) * 100)}%` }"
                  >
                    <span>{{ item.completed }}</span>
                  </div>
                </div>
                <span class="scrum-velocity-name">{{ item.name }}</span>
              </article>
            </div>
          </div>
        </div>
        <el-empty v-else description="Complete a scrum to show velocity guidance" :image-size="72" />
      </section>

      <el-card class="settings-block scrum-table-card" v-loading="loading">
        <template #header>
          <div class="epic-table-header">
            <strong>Triggered task backlog</strong>
            <span>{{ selectedTasks.length }} selected</span>
          </div>
        </template>
        <el-table :data="candidateTasks" row-key="id" empty-text="No unplanned triggered tasks found" class="epic-table scrum-table">
          <el-table-column label="Scrum" width="96">
            <template #default="scope">
              <el-switch :model-value="isSelected(scope.row)" @change="(value: boolean) => setSelected(scope.row, value)" />
            </template>
          </el-table-column>
          <el-table-column label="Task" min-width="260" show-overflow-tooltip>
            <template #default="scope">
              <div class="scrum-epic-cell">
                <strong>{{ scope.row.title }}</strong>
                <span>{{ triggerDisplay(scope.row, eventsById()) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="Priority" width="110">
            <template #default="scope">
              <el-tag effect="dark" :type="priorityTagType(priorityLabel(scope.row))">{{ priorityLabel(scope.row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Points" width="142">
            <template #default="scope">
              <el-select
                :model-value="pointsFor(scope.row)"
                size="small"
                class="story-point-select"
                @change="(value: number) => setPoints(scope.row, value)"
              >
                <el-option v-for="point in FIBONACCI_POINTS" :key="point" :label="String(point)" :value="point" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="Status" width="110">
            <template #default="scope">
              <el-tag effect="plain">{{ normalizeWorkflowStatus(scope.row).toUpperCase() }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Due" width="120">
            <template #default="scope">
              {{ formatDate(scope.row.dueDateTime?.dateTime) || '-' }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </section>
</template>
