<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createMilestone,
  deleteMilestone,
  listEpics,
  listMilestones,
  queryCachedTasks,
  updateMilestone,
} from '../lib/api'
import type { TriggerMilestone } from '../lib/types'

interface MilestoneForm {
  id: number | null
  title: string
  milestone_at: string
  location: string
  notes: string
  epic_keys: string[]
  task_ids: string[]
}

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const detailVisible = ref(false)
const milestones = ref<TriggerMilestone[]>([])
const selected = ref<TriggerMilestone | null>(null)
const epicOptions = ref<Array<{ value: string; label: string }>>([])
const taskOptions = ref<Array<{ value: string; label: string }>>([])

const form = reactive<MilestoneForm>({
  id: null,
  title: '',
  milestone_at: '',
  location: '',
  notes: '',
  epic_keys: [],
  task_ids: [],
})

const totals = computed(() => {
  const epicKeys = new Set<string>()
  const taskIds = new Set<string>()
  for (const milestone of milestones.value) {
    for (const key of milestone.epic_keys || []) epicKeys.add(key)
    for (const taskId of milestone.task_ids || []) taskIds.add(taskId)
  }
  const next = milestones.value
    .map((item) => ({ item, time: item.milestone_at ? new Date(item.milestone_at).getTime() : Number.NaN }))
    .filter(({ time }) => Number.isFinite(time) && time >= Date.now())
    .sort((a, b) => a.time - b.time)[0]?.item
  return {
    milestones: milestones.value.length,
    epics: epicKeys.size,
    tasks: taskIds.size,
    next: next?.title || 'None',
  }
})

function resetForm() {
  form.id = null
  form.title = ''
  form.milestone_at = ''
  form.location = ''
  form.notes = ''
  form.epic_keys = []
  form.task_ids = []
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(milestone: TriggerMilestone) {
  form.id = milestone.id
  form.title = milestone.title
  form.milestone_at = milestone.milestone_at || ''
  form.location = milestone.location || ''
  form.notes = milestone.notes || ''
  form.epic_keys = [...(milestone.epic_keys || [])]
  form.task_ids = [...(milestone.task_ids || [])]
  dialogVisible.value = true
}

function openDetail(milestone: TriggerMilestone) {
  selected.value = milestone
  detailVisible.value = true
}

function formatDate(value?: string | null) {
  if (!value) return 'No date'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

async function loadData() {
  loading.value = true
  try {
    const [milestonesData, epicsData, tasksData] = await Promise.all([
      listMilestones(),
      listEpics(),
      queryCachedTasks(),
    ])
    milestones.value = milestonesData.items
    epicOptions.value = epicsData.items.map((epic) => ({
      value: epic.epic_key,
      label: `${epic.epic_key} - ${epic.name || 'Unnamed Epic'}`,
    }))
    taskOptions.value = tasksData.items
      .filter((task) => task.status !== 'completed')
      .map((task) => ({
        value: task.taskId,
        label: task.title || task.taskId,
      }))
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load milestones')
  } finally {
    loading.value = false
  }
}

async function saveMilestone() {
  if (!form.title.trim()) {
    ElMessage.warning('Title is required')
    return
  }

  saving.value = true
  try {
    const payload = {
      title: form.title.trim(),
      milestone_at: form.milestone_at || null,
      location: form.location.trim() || null,
      notes: form.notes.trim() || null,
      epic_keys: form.epic_keys,
      task_ids: form.task_ids,
    }
    if (form.id) {
      await updateMilestone(form.id, payload)
    } else {
      await createMilestone(payload)
    }
    dialogVisible.value = false
    await loadData()
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to save milestone')
  } finally {
    saving.value = false
  }
}

async function removeMilestone(milestone: TriggerMilestone) {
  try {
    await ElMessageBox.confirm(`Delete milestone "${milestone.title}"?`, 'Delete Milestone', {
      type: 'warning',
      confirmButtonText: 'Delete',
      cancelButtonText: 'Cancel',
    })
    await deleteMilestone(milestone.id)
    detailVisible.value = false
    await loadData()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error((error as Error).message || 'Failed to delete milestone')
  }
}

onMounted(loadData)
</script>

<template>
  <section class="page-shell milestone-page">
    <header class="page-head milestone-head">
      <div>
        <h1>Milestones</h1>
        <p>Timeline of important checkpoints with linked epics and tasks</p>
      </div>
      <div class="actions">
        <el-button type="primary" @click="openCreate">Create Milestone</el-button>
      </div>
    </header>

    <section class="milestone-kpis">
      <div class="milestone-kpi milestone-kpi-total">
        <span class="metric-label">Milestones</span>
        <strong class="metric-value">{{ totals.milestones }}</strong>
      </div>
      <div class="milestone-kpi milestone-kpi-epics">
        <span class="metric-label">Linked Epics</span>
        <strong class="metric-value">{{ totals.epics }}</strong>
      </div>
      <div class="milestone-kpi milestone-kpi-tasks">
        <span class="metric-label">Linked Tasks</span>
        <strong class="metric-value">{{ totals.tasks }}</strong>
      </div>
      <div class="milestone-kpi milestone-kpi-next">
        <span class="metric-label">Next</span>
        <strong class="metric-value milestone-next-title">{{ totals.next }}</strong>
      </div>
    </section>

    <el-skeleton v-if="loading" :rows="8" animated />

    <section v-else class="milestone-curve">
      <svg class="milestone-s-line" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d="M50 0 C15 18 15 32 50 50 C85 68 85 82 50 100" />
      </svg>
      <article
        v-for="(milestone, index) in milestones"
        :key="milestone.id"
        class="milestone-node"
        :class="index % 2 === 0 ? 'milestone-node-left' : 'milestone-node-right'"
      >
        <div class="milestone-dot">{{ index + 1 }}</div>
        <div class="milestone-card">
          <div class="milestone-card-head">
            <span>{{ formatDate(milestone.milestone_at) }}</span>
            <el-tag v-if="milestone.location" size="small" effect="plain">{{ milestone.location }}</el-tag>
          </div>
          <h2>{{ milestone.title }}</h2>
          <p v-if="milestone.notes">{{ milestone.notes }}</p>
          <div class="milestone-summary">
            <button type="button" @click="openDetail(milestone)">
              <strong>{{ milestone.summary.epics }}</strong>
              <span>Epics</span>
            </button>
            <button type="button" @click="openDetail(milestone)">
              <strong>{{ milestone.summary.tasks }}</strong>
              <span>Tasks</span>
            </button>
            <el-button size="small" @click="openEdit(milestone)">Edit</el-button>
          </div>
        </div>
      </article>
      <el-empty v-if="!milestones.length" description="No milestones yet" />
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? 'Edit Milestone' : 'Create Milestone'"
      width="680px"
      class="task-dialog"
    >
      <el-form label-position="top" class="task-form">
        <el-form-item label="Title">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="24" :md="12">
            <el-form-item label="Time">
              <el-input v-model="form.milestone_at" type="datetime-local" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="Location">
              <el-input v-model="form.location" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="Epics">
          <el-select v-model="form.epic_keys" multiple filterable class="field-full" placeholder="Link epics">
            <el-option v-for="option in epicOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="Tasks">
          <el-select v-model="form.task_ids" multiple filterable class="field-full" placeholder="Link tasks">
            <el-option v-for="option in taskOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="Notes">
          <el-input v-model="form.notes" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="saveMilestone">Save</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="Milestone Details" size="420px">
      <section v-if="selected" class="milestone-detail">
        <header>
          <span>{{ formatDate(selected.milestone_at) }}</span>
          <h2>{{ selected.title }}</h2>
          <p v-if="selected.location">{{ selected.location }}</p>
        </header>
        <p v-if="selected.notes" class="milestone-detail-notes">{{ selected.notes }}</p>

        <h3>Epics</h3>
        <div class="milestone-link-list">
          <div v-for="epic in selected.epics" :key="epic.epic_key" class="milestone-link-item">
            <strong>{{ epic.epic_key }}</strong>
            <span>{{ epic.name }}</span>
            <el-tag v-if="epic.priority" size="small" effect="plain">{{ epic.priority }}</el-tag>
          </div>
          <el-empty v-if="!selected.epics.length" description="No linked epics" />
        </div>

        <h3>Tasks</h3>
        <div class="milestone-link-list">
          <router-link
            v-for="task in selected.tasks"
            :key="task.task_id"
            class="milestone-link-item milestone-task-link"
            :to="task.list_id ? `/tasks/${task.list_id}/${task.task_id}` : '#'"
          >
            <strong>{{ task.title }}</strong>
            <span>{{ task.status || 'notStarted' }}</span>
          </router-link>
          <el-empty v-if="!selected.tasks.length" description="No linked tasks" />
        </div>

        <footer class="milestone-detail-actions">
          <el-button @click="openEdit(selected)">Edit</el-button>
          <el-button type="danger" plain @click="removeMilestone(selected)">Delete</el-button>
        </footer>
      </section>
    </el-drawer>
  </section>
</template>
