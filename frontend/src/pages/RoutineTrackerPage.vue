<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchAllTasks, listRoutineChecks, listTriggerEvents, setRoutineCheck } from '../lib/api'
import { triggerDisplay } from '../lib/triggerSignal'
import type { TodoTask, TriggerEvent } from '../lib/types'

function toLocalDateInputValue(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function startOfWeek(date: Date) {
  const copy = new Date(date)
  const dayOffset = (copy.getDay() + 6) % 7
  copy.setDate(copy.getDate() - dayOffset)
  copy.setHours(0, 0, 0, 0)
  return copy
}

function addDays(date: Date, days: number) {
  const copy = new Date(date)
  copy.setDate(copy.getDate() + days)
  return copy
}

function dateFromLocalInput(value: string) {
  const [year = 0, month = 1, day = 1] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function taskKey(task: TodoTask) {
  return `${task.listId}:${task.id}`
}

function routineCheckKey(listId: string, taskId: string, checkDate: string) {
  return `${listId}:${taskId}:${checkDate}`
}

function routineCellKey(task: TodoTask, checkDate: string) {
  return routineCheckKey(task.listId, task.id, checkDate)
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

function recurrenceType(task: TodoTask) {
  return String(task.recurrence?.pattern?.type || '').toLowerCase()
}

function routineFrequency(task: TodoTask): 'Daily' | 'Weekly' | null {
  const ref = String(extension(task)?.triggerRef || '').toLowerCase()
  const type = recurrenceType(task)
  if (ref === 'date:daily' || type === 'daily') return 'Daily'
  if (ref === 'date:weekly' || type === 'weekly' || type === 'relativeweekly') return 'Weekly'
  return null
}

function isRoutineTask(task: TodoTask) {
  return routineFrequency(task) !== null
}

function dueTime(task: TodoTask) {
  const value = task.dueDateTime?.dateTime
  if (!value) return Number.POSITIVE_INFINITY
  const time = Date.parse(value)
  return Number.isNaN(time) ? Number.POSITIVE_INFINITY : time
}

function compareDueTime(a: TodoTask, b: TodoTask) {
  const aDue = dueTime(a)
  const bDue = dueTime(b)
  const aHasDue = Number.isFinite(aDue)
  const bHasDue = Number.isFinite(bDue)
  if (aHasDue && bHasDue) return aDue - bDue
  if (aHasDue) return -1
  if (bHasDue) return 1
  return 0
}

function routineDueLabel(task: TodoTask) {
  const due = dueTime(task)
  if (!Number.isFinite(due)) return 'No due date'
  return due <= Date.now() ? 'Due' : 'Upcoming'
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const at = new Date(value)
  return Number.isNaN(at.getTime()) ? '' : at.toLocaleDateString()
}

const loading = ref(false)
const checkingRoutineCell = ref<string | null>(null)
const tasks = ref<TodoTask[]>([])
const triggerEvents = ref<TriggerEvent[]>([])
const routineChecks = ref(new Set<string>())
const routineWeekStart = ref(toLocalDateInputValue(startOfWeek(new Date())))

const routineWeekDays = computed(() => {
  const start = dateFromLocalInput(routineWeekStart.value)
  return Array.from({ length: 7 }, (_, index) => {
    const date = addDays(start, index)
    return {
      index,
      date: toLocalDateInputValue(date),
      label: `Day ${index + 1}`,
      shortDate: date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    }
  })
})
const routineWeekEnd = computed(() => routineWeekDays.value[6]?.date || routineWeekStart.value)
const routineWeekLabel = computed(() => `${formatDate(routineWeekStart.value)} - ${formatDate(routineWeekEnd.value)}`)

const routineTasks = computed(() =>
  tasks.value
    .filter((task) => !isCompletedStatus(task.status))
    .filter(isRoutineTask)
    .sort((a, b) => {
      const dueDiff = compareDueTime(a, b)
      if (dueDiff !== 0) return dueDiff
      const frequencyDiff = String(routineFrequency(a)).localeCompare(String(routineFrequency(b)))
      if (frequencyDiff !== 0) return frequencyDiff
      return a.title.localeCompare(b.title)
    }),
)
const dueRoutineCount = computed(() => routineTasks.value.filter((task) => routineDueLabel(task) === 'Due').length)
const dailyRoutineCount = computed(() => routineTasks.value.filter((task) => routineFrequency(task) === 'Daily').length)
const weeklyRoutineCount = computed(() => routineTasks.value.filter((task) => routineFrequency(task) === 'Weekly').length)
const visibleRoutineCheckKeys = computed(() => {
  const keys = new Set<string>()
  for (const task of routineTasks.value) {
    if (routineFrequency(task) === 'Weekly') {
      keys.add(routineCellKey(task, routineWeekStart.value))
    } else {
      for (const day of routineWeekDays.value) keys.add(routineCellKey(task, day.date))
    }
  }
  return keys
})
const checkedRoutineCount = computed(() => [...routineChecks.value].filter((key) => visibleRoutineCheckKeys.value.has(key)).length)

function isRoutineChecked(task: TodoTask, checkDate: string) {
  return routineChecks.value.has(routineCellKey(task, checkDate))
}

async function setRoutineChecked(task: TodoTask, checkDate: string, checked: boolean) {
  const key = routineCellKey(task, checkDate)
  checkingRoutineCell.value = key
  try {
    await setRoutineCheck({
      list_id: task.listId,
      task_id: task.id,
      check_date: checkDate,
      checked,
    })
    const next = new Set(routineChecks.value)
    if (checked) next.add(key)
    else next.delete(key)
    routineChecks.value = next
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update routine check')
  } finally {
    checkingRoutineCell.value = null
  }
}

async function loadRoutineChecks() {
  const data = await listRoutineChecks(routineWeekStart.value, routineWeekEnd.value)
  routineChecks.value = new Set(data.items.map((item) => routineCheckKey(item.list_id, item.task_id, item.check_date)))
}

async function shiftRoutineWeek(days: number) {
  routineWeekStart.value = toLocalDateInputValue(addDays(dateFromLocalInput(routineWeekStart.value), days))
  try {
    await loadRoutineChecks()
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load routine checks')
  }
}

async function resetRoutineWeek() {
  routineWeekStart.value = toLocalDateInputValue(startOfWeek(new Date()))
  try {
    await loadRoutineChecks()
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load routine checks')
  }
}

async function loadRoutineTracker() {
  loading.value = true
  try {
    const [taskData, eventsData, routineData] = await Promise.all([
      fetchAllTasks(),
      listTriggerEvents(),
      listRoutineChecks(routineWeekStart.value, routineWeekEnd.value),
    ])
    tasks.value = taskData.tasks
    triggerEvents.value = eventsData.items
    routineChecks.value = new Set(routineData.items.map((item) => routineCheckKey(item.list_id, item.task_id, item.check_date)))
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load routine tracker')
  } finally {
    loading.value = false
  }
}

onMounted(loadRoutineTracker)
</script>

<template>
  <section class="page-shell scrum-page routine-page">
    <header class="page-head">
      <div>
        <h1>Routine Tracker</h1>
        <p>{{ routineWeekLabel }}</p>
      </div>
    </header>

    <section class="routine-checker-panel" v-loading="loading">
      <div class="routine-checker-head">
        <div>
          <strong>Routine sheet</strong>
          <span>Daily and weekly tasks are tracked here, outside scrum story points.</span>
        </div>
        <div class="routine-metrics">
          <el-button size="small" plain @click="shiftRoutineWeek(-7)">Previous</el-button>
          <el-button size="small" plain @click="resetRoutineWeek">This Week</el-button>
          <el-button size="small" plain @click="shiftRoutineWeek(7)">Next</el-button>
          <el-tag type="warning" effect="plain">{{ dueRoutineCount }} due</el-tag>
          <el-tag type="success" effect="plain">{{ dailyRoutineCount }} daily</el-tag>
          <el-tag type="info" effect="plain">{{ weeklyRoutineCount }} weekly</el-tag>
          <el-tag effect="plain">{{ checkedRoutineCount }} checked</el-tag>
        </div>
      </div>
      <el-table
        :data="routineTasks"
        :row-key="taskKey"
        empty-text="No daily or weekly routines found"
        class="epic-table routine-table routine-sheet"
      >
        <el-table-column label="Routine" min-width="260" show-overflow-tooltip>
          <template #default="scope">
            <div class="scrum-epic-cell">
              <strong>{{ scope.row.title }}</strong>
              <span>{{ triggerDisplay(scope.row, eventsById()) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Cadence" width="112">
          <template #default="scope">
            <el-tag effect="plain">{{ routineFrequency(scope.row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          v-for="day in routineWeekDays"
          :key="day.date"
          min-width="92"
          align="center"
        >
          <template #header>
            <div class="routine-day-head">
              <strong>{{ day.label }}</strong>
              <span>{{ day.shortDate }}</span>
            </div>
          </template>
          <template #default="scope">
            <el-checkbox
              v-if="routineFrequency(scope.row) === 'Daily' || day.index === 0"
              :model-value="isRoutineChecked(scope.row, routineFrequency(scope.row) === 'Weekly' ? routineWeekStart : day.date)"
              :disabled="checkingRoutineCell === routineCellKey(scope.row, routineFrequency(scope.row) === 'Weekly' ? routineWeekStart : day.date)"
              @change="(value: boolean) => setRoutineChecked(scope.row, routineFrequency(scope.row) === 'Weekly' ? routineWeekStart : day.date, value)"
            >
              {{ routineFrequency(scope.row) === 'Weekly' ? 'Week' : '' }}
            </el-checkbox>
            <span v-else class="routine-empty-cell">-</span>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </section>
</template>
