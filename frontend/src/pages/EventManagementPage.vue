<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createTriggerEvent, deleteTriggerEvent, listTriggerEvents, updateTriggerEvent } from '../lib/api'
import type { TriggerEvent } from '../lib/types'

const loading = ref(false)
const creating = ref(false)
const saving = ref(false)
const events = ref<TriggerEvent[]>([])
const form = reactive({ name: '' })
const editingEventId = ref<number | null>(null)
const editingName = ref('')

async function loadEvents() {
  loading.value = true
  try {
    const result = await listTriggerEvents()
    events.value = result.items
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load events')
  } finally {
    loading.value = false
  }
}

async function createEvent() {
  if (!form.name.trim()) {
    ElMessage.warning('Event name is required')
    return
  }

  creating.value = true
  try {
    await createTriggerEvent({ name: form.name.trim() })
    form.name = ''
    await loadEvents()
    ElMessage.success('Event created')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to create event')
  } finally {
    creating.value = false
  }
}

function startEdit(event: TriggerEvent) {
  editingEventId.value = event.id
  editingName.value = event.name
}

function cancelEdit() {
  editingEventId.value = null
  editingName.value = ''
}

async function saveEdit(event: TriggerEvent) {
  const nextName = editingName.value.trim()
  if (!nextName) {
    ElMessage.warning('Event name is required')
    return
  }
  if (nextName === event.name) {
    cancelEdit()
    return
  }
  try {
    saving.value = true
    await updateTriggerEvent(event.id, { name: nextName })
    cancelEdit()
    await loadEvents()
    ElMessage.success('Event updated')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update event')
  } finally {
    saving.value = false
  }
}

async function markOccurred(event: TriggerEvent, active: boolean) {
  try {
    await updateTriggerEvent(event.id, { is_active: active })
    await loadEvents()
    ElMessage.success(active ? 'Event marked occurred' : 'Event reset')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update event state')
  }
}

async function removeEvent(eventId: number) {
  try {
    await deleteTriggerEvent(eventId)
    events.value = events.value.filter((item) => item.id !== eventId)
    ElMessage.success('Event deleted')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to delete event')
  }
}

onMounted(loadEvents)
</script>

<template>
  <section class="page-shell">
    <header class="page-head">
      <div>
        <h1>Event Triggers</h1>
        <p>Create events and mark whether they happened. Tasks linked to active events move to Triggered Board.</p>
      </div>
    </header>

    <el-card>
      <template #header>
        <strong>Create event trigger</strong>
      </template>
      <div class="event-create-row">
        <el-input v-model="form.name" placeholder="Deployment completed" maxlength="120" />
        <el-button type="primary" :loading="creating" @click="createEvent">Create</el-button>
      </div>
    </el-card>

    <el-card class="settings-block" v-loading="loading">
      <template #header>
        <strong>Events</strong>
      </template>
      <el-table :data="events" empty-text="No events yet">
        <el-table-column label="Name" min-width="260">
          <template #default="scope">
            <el-input
              v-if="editingEventId === scope.row.id"
              v-model="editingName"
              maxlength="120"
            />
            <span v-else>{{ scope.row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Occurred" width="130">
          <template #default="scope">
            <el-tag :type="scope.row.is_active ? 'success' : 'info'">
              {{ scope.row.is_active ? 'Yes' : 'No' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Occurred At" min-width="180">
          <template #default="scope">
            {{ scope.row.occurred_at ? new Date(scope.row.occurred_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="280">
          <template #default="scope">
            <el-button
              v-if="editingEventId !== scope.row.id"
              size="small"
              @click="startEdit(scope.row)"
            >
              Edit
            </el-button>
            <el-button
              v-else
              size="small"
              type="primary"
              :loading="saving"
              @click="saveEdit(scope.row)"
            >
              Save
            </el-button>
            <el-button
              v-if="editingEventId === scope.row.id"
              size="small"
              @click="cancelEdit"
            >
              Cancel
            </el-button>
            <el-button
              size="small"
              :type="scope.row.is_active ? 'warning' : 'success'"
              plain
              @click="markOccurred(scope.row, !scope.row.is_active)"
            >
              {{ scope.row.is_active ? 'Reset' : 'Mark Occurred' }}
            </el-button>
            <el-popconfirm title="Delete this event?" @confirm="removeEvent(scope.row.id)">
              <template #reference>
                <el-button type="danger" plain size="small">Delete</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>
