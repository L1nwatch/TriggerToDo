<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import TaskForm from '../components/TaskForm.vue'
import { deleteTask, getTask, listEpics, listTodoLists, listTriggerEvents, updateTask } from '../lib/api'
import { builtInTriggerOptions, isDateTriggerRef } from '../lib/triggerCatalog'
import { defaultTaskForm, formFromTask, taskPayloadFromForm, type TaskFormModel } from '../lib/taskForm'
import type { TodoList, TriggerEvent } from '../lib/types'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const lists = ref<TodoList[]>([])
const triggerEvents = ref<TriggerEvent[]>([])
const epicOptions = ref<Array<{ value: string; label: string }>>([])
const triggerLoading = ref(false)
const epicLoading = ref(false)
const form = reactive<TaskFormModel>(defaultTaskForm(''))

const listId = String(route.params.listId)
const taskId = String(route.params.taskId)

async function loadTask() {
  loading.value = true
  try {
    triggerLoading.value = true
    epicLoading.value = true
    const [listsData, task, eventsData, epicsData] = await Promise.all([
      listTodoLists(),
      getTask(listId, taskId),
      listTriggerEvents(),
      listEpics(),
    ])
    lists.value = listsData
    triggerEvents.value = eventsData.items
    epicOptions.value = epicsData.items.map((epic) => ({
      value: epic.epic_key,
      label: epic.name || 'Unnamed Epic',
    }))
    if (!task) {
      ElMessage.error('Task not found')
      router.replace({ path: '/board/triggered' })
      return
    }
    Object.assign(form, formFromTask(task))
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load task')
  } finally {
    triggerLoading.value = false
    epicLoading.value = false
    loading.value = false
  }
}

async function save() {
  if (!form.title.trim()) {
    ElMessage.warning('Title is required')
    return
  }
  if (isDateTriggerRef(form.triggerRef) && !form.dueAt) {
    ElMessage.warning('Date trigger requires due date')
    return
  }

  saving.value = true
  try {
    await updateTask(listId, taskId, taskPayloadFromForm(form))
    ElMessage.success('Task updated')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update task')
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    await deleteTask(listId, taskId)
    ElMessage.success('Task deleted')
    router.replace({ path: '/board/triggered' })
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to delete task')
  }
}

onMounted(loadTask)
</script>

<template>
  <section class="page-shell">
    <header class="page-head">
      <div>
        <h1>Task Detail</h1>
        <p>List: {{ listId }}</p>
      </div>
      <div class="actions">
        <el-button @click="$router.push('/board/triggered')">Back</el-button>
      </div>
    </header>

    <el-card v-loading="loading">
      <TaskForm
        :model="form"
        :lists="lists"
        :readonly-list="true"
        :trigger-options="[
          ...builtInTriggerOptions(),
          ...triggerEvents.map((event) => ({ value: `event:${event.id}`, label: `event-trigger: ${event.name}${event.is_active ? ' (occurred)' : ''}` })),
        ]"
        :trigger-loading="triggerLoading"
        :epic-options="epicOptions"
        :epic-loading="epicLoading"
      />
      <div class="detail-actions">
        <el-button type="danger" plain @click="remove">Delete</el-button>
        <el-button type="primary" :loading="saving" @click="save">Save changes</el-button>
      </div>
    </el-card>
  </section>
</template>
