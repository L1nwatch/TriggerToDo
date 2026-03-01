<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listEpics, queryCachedTasks, updateEpic } from '../lib/api'

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
const editMode = ref(false)
const rows = ref<EpicRow[]>([])

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

function statusTagType(status?: string) {
  const value = String(status || '').toLowerCase()
  if (!value) return 'info'
  if (value.includes('progress') || value.includes('doing') || value.includes('active')) return 'warning'
  if (value.includes('done') || value.includes('closed') || value.includes('resolved') || value.includes('complete')) return 'success'
  if (value.includes('block')) return 'danger'
  return 'info'
}

const total = computed(() => rows.value.length)
const highPriorityCount = computed(() => rows.value.filter((row) => row.priorityTag === 'P0' || row.priorityTag === 'P1').length)
const linkedTaskTotal = computed(() => rows.value.reduce((sum, row) => sum + row.linkedTasks, 0))

async function loadEpics() {
  loading.value = true
  try {
    const [epicsData, tasksData] = await Promise.all([listEpics(), queryCachedTasks()])
    const linkedByEpic = new Map<string, number>()

    for (const task of tasksData.items) {
      if (String(task.status || '').toLowerCase() === 'completed') continue
      const epicKey = String(task.epicKey || '').trim().toUpperCase()
      if (!epicKey) continue
      linkedByEpic.set(epicKey, (linkedByEpic.get(epicKey) || 0) + 1)
    }

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

async function saveEpic(row: EpicRow) {
  const name = row.name.trim()
  if (!name) {
    ElMessage.warning('Epic name is required')
    return
  }

  row.saving = true
  try {
    await updateEpic(row.id, { name, priority: row.priorityTag })
    ElMessage.success(`Updated ${row.key}`)
    await loadEpics()
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update epic')
  } finally {
    row.saving = false
  }
}

onMounted(loadEpics)
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

    <el-table :data="rows" v-loading="loading" empty-text="No epics found" class="epic-table">
      <el-table-column label="Name" min-width="460">
        <template #default="scope">
          <template v-if="editMode">
            <el-input v-model="scope.row.name" />
          </template>
          <template v-else>
            {{ scope.row.name }}
          </template>
        </template>
      </el-table-column>
      <el-table-column label="Priority" width="120">
        <template #default="scope">
          <template v-if="editMode">
            <el-select v-model="scope.row.priorityTag">
              <el-option label="P0" value="P0" />
              <el-option label="P1" value="P1" />
              <el-option label="P2" value="P2" />
              <el-option label="P3" value="P3" />
            </el-select>
          </template>
          <template v-else>
            <el-tag effect="dark" :type="priorityTagType(scope.row.priorityTag)">{{ scope.row.priorityTag }}</el-tag>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="Linked Tasks" width="130">
        <template #default="scope">
          <el-tag effect="plain" type="success" class="linked-tag">{{ scope.row.linkedTasks }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Status" width="160">
        <template #default="scope">
          <el-tag effect="plain" :type="statusTagType(scope.row.status)">{{ scope.row.status || 'Unknown' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="editMode" label="Save" width="100">
        <template #default="scope">
          <el-button size="small" type="primary" :loading="scope.row.saving" @click="saveEpic(scope.row)">Save</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>
