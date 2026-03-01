<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { createTriggerEvent } from '../lib/api'
import type { TodoList } from '../lib/types'
import type { TaskFormModel } from '../lib/taskForm'

interface Props {
  model: TaskFormModel
  lists: TodoList[]
  readonlyList?: boolean
  hideWorkflowStatus?: boolean
  triggerOptions?: Array<{
    value: string
    label: string
    disabled?: boolean
  }>
  triggerLoading?: boolean
  epicOptions?: Array<{
    value: string
    label: string
  }>
  epicLoading?: boolean
}

const props = defineProps<Props>()

const CREATE_EVENT_OPTION_VALUE = '__create_event__'
const createdEventOptions = ref<Array<{ value: string; label: string; disabled?: boolean }>>([])
const triggerType = ref<'none' | 'date' | 'event'>('none')
const selectedDateTrigger = ref('date')
const selectedEventTrigger = ref('')
const showDateFields = computed(() => triggerType.value === 'date')
const showDateInterval = computed(() => showDateFields.value && selectedDateTrigger.value !== 'date')
const dateIntervalUnitLabel = computed(() => {
  if (selectedDateTrigger.value === 'date:daily') return 'day(s)'
  if (selectedDateTrigger.value === 'date:weekly') return 'week(s)'
  if (selectedDateTrigger.value === 'date:monthly') return 'month(s)'
  if (selectedDateTrigger.value === 'date:yearly') return 'year(s)'
  return 'day(s)'
})

const dateTriggerOptions = computed(() => {
  const fromProps = (props.triggerOptions || []).filter((option) => {
    const value = String(option.value || '')
    return value === 'date' || value.startsWith('date:')
  })
  if (fromProps.length) return fromProps
  return [
    { value: 'date', label: 'date-trigger (activate when due date arrives)' },
    { value: 'date:daily', label: 'daily-trigger (due-date based)' },
    { value: 'date:weekly', label: 'weekly-trigger (due-date based)' },
    { value: 'date:monthly', label: 'monthly-trigger (due-date based)' },
    { value: 'date:yearly', label: 'yearly-trigger (due-date based)' },
  ]
})

function parsePriorityRank(value?: string): number {
  const text = String(value || '').toLowerCase()
  if (text.includes('p0') || text.includes('highest') || text.includes('critical') || text.includes('blocker')) return 0
  if (text.includes('p1') || text.includes('high') || text.includes('major')) return 1
  if (text.includes('p2') || text.includes('medium') || text.includes('normal')) return 2
  if (text.includes('p3') || text.includes('low') || text.includes('minor')) return 3
  return 9
}

const sortedEpicOptions = computed(() => {
  const options = [...(props.epicOptions || [])]
  return options.sort((a, b) => {
    const rankDiff = parsePriorityRank(a.label) - parsePriorityRank(b.label)
    if (rankDiff !== 0) return rankDiff
    return a.label.localeCompare(b.label)
  })
})

const eventTriggerOptions = computed(() => {
  const fromProps = (props.triggerOptions || []).filter((option) => String(option.value || '').startsWith('event:'))
  const merged = [...fromProps, ...createdEventOptions.value]
  const deduped = new Map<string, { value: string; label: string; disabled?: boolean }>()
  for (const option of merged) deduped.set(option.value, option)
  return [...deduped.values()]
})

const eventTriggerOptionsWithCreate = computed(() => [
  ...eventTriggerOptions.value,
  { value: CREATE_EVENT_OPTION_VALUE, label: 'Create new event...' },
])

function syncTriggerStateFromRef(value: string) {
  const ref = String(value || '').trim().toLowerCase()
  if (!ref) {
    triggerType.value = 'none'
    selectedEventTrigger.value = ''
    selectedDateTrigger.value = dateTriggerOptions.value[0]?.value || 'date'
    return
  }
  if (ref.startsWith('event:')) {
    triggerType.value = 'event'
    selectedEventTrigger.value = value
    return
  }
  if (ref === 'date' || ref.startsWith('date:')) {
    triggerType.value = 'date'
    if (ref === 'date:custom') {
      selectedDateTrigger.value = 'date:weekly'
      props.model.triggerRef = 'date:weekly'
      return
    }
    selectedDateTrigger.value = value
    return
  }
  triggerType.value = 'none'
}

async function createEventInline(): Promise<string | null> {
  try {
    const result = await ElMessageBox.prompt('Event name', 'Create Event Trigger', {
      inputPlaceholder: 'e.g. Back to China',
      inputPattern: /.+/,
      inputErrorMessage: 'Event name is required',
      confirmButtonText: 'Create',
      cancelButtonText: 'Cancel',
    })
    const name = String(result.value || '').trim()
    if (!name) return null
    const created = await createTriggerEvent({ name })
    const value = `event:${created.id}`
    const label = `event-trigger: ${created.name}${created.is_active ? ' (occurred)' : ''}`
    createdEventOptions.value.push({ value, label, disabled: false })
    triggerType.value = 'event'
    selectedEventTrigger.value = value
    props.model.triggerRef = value
    ElMessage.success('Event trigger created')
    return value
  } catch {
    // canceled or failed
    return null
  }
}

async function onEventTriggerChange(value: string) {
  if (value !== CREATE_EVENT_OPTION_VALUE) return
  const createdValue = await createEventInline()
  if (createdValue) {
    selectedEventTrigger.value = createdValue
    return
  }
  const current = String(props.model.triggerRef || '')
  selectedEventTrigger.value = current.startsWith('event:') ? current : ''
}

watch(
  () => props.model.triggerRef,
  (value) => {
    syncTriggerStateFromRef(String(value || ''))
    const ref = String(value || '').trim().toLowerCase()
    if (ref.startsWith('event:')) {
      props.model.dueAt = ''
      props.model.recurrenceType = 'none'
      props.model.recurrenceInterval = 1
      return
    }
    if (ref === 'date') {
      props.model.recurrenceType = 'none'
      props.model.recurrenceInterval = 1
      return
    }
    if (ref === 'date:daily') {
      props.model.recurrenceType = 'daily'
      if (!props.model.recurrenceInterval || props.model.recurrenceInterval < 1) props.model.recurrenceInterval = 1
    }
    if (ref === 'date:weekly') {
      props.model.recurrenceType = 'weekly'
      if (!props.model.recurrenceInterval || props.model.recurrenceInterval < 1) props.model.recurrenceInterval = 1
    }
    if (ref === 'date:monthly') {
      props.model.recurrenceType = 'monthly'
      if (!props.model.recurrenceInterval || props.model.recurrenceInterval < 1) props.model.recurrenceInterval = 1
    }
    if (ref === 'date:yearly') {
      props.model.recurrenceType = 'yearly'
      if (!props.model.recurrenceInterval || props.model.recurrenceInterval < 1) props.model.recurrenceInterval = 1
    }
  },
  { immediate: true },
)

watch(
  [triggerType, selectedDateTrigger, selectedEventTrigger],
  () => {
    if (triggerType.value === 'none') {
      props.model.triggerRef = ''
      return
    }
    if (triggerType.value === 'date') {
      props.model.triggerRef = selectedDateTrigger.value || dateTriggerOptions.value[0]?.value || 'date'
      return
    }
    if (selectedEventTrigger.value === CREATE_EVENT_OPTION_VALUE) return
    if (!selectedEventTrigger.value) return
    props.model.triggerRef = selectedEventTrigger.value
  },
)

watch(
  triggerType,
  (value) => {
    if (value === 'event') {
      props.model.dueAt = ''
      props.model.recurrenceType = 'none'
      props.model.recurrenceInterval = 1
      if (!selectedEventTrigger.value || selectedEventTrigger.value === CREATE_EVENT_OPTION_VALUE) {
        const current = String(props.model.triggerRef || '')
        if (current.startsWith('event:')) {
          selectedEventTrigger.value = current
          return
        }
        const fallback = eventTriggerOptions.value[0]?.value || ''
        if (fallback) {
          selectedEventTrigger.value = fallback
        }
      }
      return
    }
    if (value === 'none') {
      props.model.dueAt = ''
      props.model.recurrenceType = 'none'
      props.model.recurrenceInterval = 1
    }
  },
)
</script>

<template>
  <el-form label-position="top" class="task-form" @submit.prevent>
    <el-row :gutter="12">
      <el-col :xs="24">
        <el-form-item label="Title" required>
          <el-input v-model="model.title" maxlength="240" show-word-limit placeholder="What needs to get done?" />
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col v-if="!hideWorkflowStatus" :xs="24" :md="12">
        <el-form-item label="Workflow Status">
          <el-select v-model="model.wfStatus" class="field-full">
            <el-option label="pending-trigger" value="wait-for-trigger" />
            <el-option label="todo" value="todo" />
            <el-option label="doing" value="doing" />
          </el-select>
        </el-form-item>
      </el-col>
      <el-col :xs="24" :md="hideWorkflowStatus ? 24 : 12">
        <el-form-item label="Epic">
          <el-select
            v-model="model.epicKey"
            class="field-full"
            clearable
            filterable
            :loading="epicLoading"
            placeholder="Select epic"
          >
            <el-option
              v-for="option in sortedEpicOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :xs="24" :md="12">
        <el-form-item label="Trigger Type">
          <el-select v-model="triggerType" class="field-full">
            <el-option label="none" value="none" />
            <el-option label="date-related trigger" value="date" />
            <el-option label="event-related trigger" value="event" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row v-if="triggerType === 'date'" :gutter="12">
      <el-col :xs="24" :md="12">
        <el-form-item label="Date Trigger">
          <el-select
            v-model="selectedDateTrigger"
            class="field-full"
            filterable
            :loading="triggerLoading"
            placeholder="Select date trigger"
          >
            <el-option
              v-for="option in dateTriggerOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
              :disabled="option.disabled"
            />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row v-if="triggerType === 'event'" :gutter="12">
      <el-col :xs="24" :md="12">
        <el-form-item label="Event Trigger">
          <el-select
            v-model="selectedEventTrigger"
            class="field-full"
            clearable
            filterable
            :loading="triggerLoading"
            placeholder="Select existing event"
            @change="onEventTriggerChange"
          >
            <el-option
              v-for="option in eventTriggerOptionsWithCreate"
              :key="option.value"
              :label="option.label"
              :value="option.value"
              :disabled="option.disabled"
            />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col v-if="showDateFields" :xs="24" :md="12">
        <el-form-item label="Due At (UTC)">
          <el-input v-model="model.dueAt" type="datetime-local" />
        </el-form-item>
      </el-col>
      <el-col v-if="showDateInterval" :xs="24" :md="12">
        <el-form-item label="Every">
          <div class="row-inline recurrence-inline recurrence-fixed">
            <el-input-number
              v-model="model.recurrenceInterval"
              :min="1"
              :max="99"
              controls-position="right"
            />
            <span class="recurrence-word">{{ dateIntervalUnitLabel }}</span>
          </div>
        </el-form-item>
      </el-col>
    </el-row>

    <el-form-item label="Notes">
      <el-input v-model="model.notes" type="textarea" :rows="4" placeholder="Additional context" />
    </el-form-item>
  </el-form>
</template>
