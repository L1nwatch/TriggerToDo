<script setup lang="ts">
import { computed } from 'vue'
import TaskForm from './TaskForm.vue'
import type { TaskFormModel } from '../lib/taskForm'
import type { TodoList } from '../lib/types'

type TriggerOption = {
  value: string
  label: string
  disabled?: boolean
}

type EpicOption = {
  value: string
  label: string
}

interface Props {
  modelValue: boolean
  model: TaskFormModel
  lists: TodoList[]
  saving?: boolean
  readonlyList?: boolean
  hideWorkflowStatus?: boolean
  triggerOptions?: TriggerOption[]
  triggerLoading?: boolean
  epicOptions?: EpicOption[]
  epicLoading?: boolean
  title?: string
  saveText?: string
}

const props = withDefaults(defineProps<Props>(), {
  saving: false,
  readonlyList: true,
  hideWorkflowStatus: false,
  title: 'Edit Task',
  saveText: 'Save',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'save'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

function closeDialog() {
  visible.value = false
}
</script>

<template>
  <el-dialog v-model="visible" :title="title" width="min(760px, 96vw)" class="task-dialog">
    <TaskForm
      :model="model"
      :lists="lists"
      :readonly-list="readonlyList"
      :hide-workflow-status="hideWorkflowStatus"
      :trigger-options="triggerOptions"
      :trigger-loading="triggerLoading"
      :epic-options="epicOptions"
      :epic-loading="epicLoading"
    />
    <template #footer>
      <el-button @click="closeDialog">Cancel</el-button>
      <el-button type="primary" :loading="saving" @click="emit('save')">{{ saveText }}</el-button>
    </template>
  </el-dialog>
</template>
