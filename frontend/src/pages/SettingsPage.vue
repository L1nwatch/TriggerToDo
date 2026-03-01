<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createTriggerRule,
  deleteTriggerRule,
  listTriggerRules,
  runTriggersNow,
  syncDelta,
  updateTriggerRule,
} from '../lib/api'
import type { TriggerRule } from '../lib/types'

const loading = ref(false)
const saving = ref(false)
const rules = ref<TriggerRule[]>([])

const form = reactive({
  name: '',
  source_pool: '',
  source_wf_status: '',
  target_pool: '',
  target_wf_status: '',
  enabled: true,
  cron_expression: '',
})

async function loadRules() {
  loading.value = true
  try {
    const result = await listTriggerRules()
    rules.value = result.items
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to load rules')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.name = ''
  form.source_pool = ''
  form.source_wf_status = ''
  form.target_pool = ''
  form.target_wf_status = ''
  form.enabled = true
  form.cron_expression = ''
}

async function createRule() {
  if (!form.name.trim()) {
    ElMessage.warning('Rule name is required')
    return
  }

  saving.value = true
  try {
    await createTriggerRule({
      name: form.name,
      source_pool: form.source_pool || undefined,
      source_wf_status: form.source_wf_status || undefined,
      target_pool: form.target_pool || undefined,
      target_wf_status: form.target_wf_status || undefined,
      enabled: form.enabled,
      cron_expression: form.cron_expression || undefined,
    })
    resetForm()
    await loadRules()
    ElMessage.success('Rule created')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to create rule')
  } finally {
    saving.value = false
  }
}

async function updateRule(rule: TriggerRule, changes: Record<string, unknown>) {
  try {
    await updateTriggerRule(rule.id, changes)
    await loadRules()
    ElMessage.success('Rule updated')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to update rule')
  }
}

async function removeRule(ruleId: number) {
  try {
    await deleteTriggerRule(ruleId)
    rules.value = rules.value.filter((rule) => rule.id !== ruleId)
    ElMessage.success('Rule deleted')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to delete rule')
  }
}

async function runNow() {
  try {
    await runTriggersNow()
    ElMessage.success('Trigger engine run started')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to run triggers')
  }
}

async function syncNow() {
  try {
    await syncDelta()
    ElMessage.success('Delta sync completed')
  } catch (error) {
    ElMessage.error((error as Error).message || 'Failed to sync')
  }
}

onMounted(loadRules)
</script>

<template>
  <section class="page-shell">
    <header class="page-head">
      <div>
        <h1>Settings</h1>
        <p>Configure trigger rules and maintenance actions</p>
      </div>
      <div class="actions">
        <el-button @click="syncNow">Run Delta Sync</el-button>
        <el-button type="warning" @click="runNow">Run Triggers Now</el-button>
      </div>
    </header>

    <el-card class="settings-block">
      <template #header>
        <strong>Create trigger rule</strong>
      </template>

      <el-form label-position="top">
        <el-row :gutter="12">
          <el-col :xs="24" :md="8">
            <el-form-item label="Name" required>
              <el-input v-model="form.name" placeholder="Move blocked work items" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="4">
            <el-form-item label="Source pool">
              <el-input v-model="form.source_pool" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="4">
            <el-form-item label="Source status">
              <el-input v-model="form.source_wf_status" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="4">
            <el-form-item label="Target pool">
              <el-input v-model="form.target_pool" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="4">
            <el-form-item label="Target status">
              <el-input v-model="form.target_wf_status" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="12">
          <el-col :xs="24" :md="8">
            <el-form-item label="Cron expression (optional)">
              <el-input v-model="form.cron_expression" placeholder="*/5 * * * *" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="6">
            <el-form-item label="Enabled">
              <el-switch v-model="form.enabled" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="10" class="end-col">
            <el-button type="primary" :loading="saving" @click="createRule">Create Rule</el-button>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="settings-block" v-loading="loading">
      <template #header>
        <strong>Existing rules</strong>
      </template>

      <el-table :data="rules" empty-text="No trigger rules yet">
        <el-table-column prop="name" label="Name" min-width="220">
          <template #default="scope">
            <el-input
              :model-value="scope.row.name"
              @change="(value: string) => updateRule(scope.row, { name: value })"
            />
          </template>
        </el-table-column>
        <el-table-column label="Match" min-width="180">
          <template #default="scope">
            <code>{{ scope.row.source_pool || '*' }} / {{ scope.row.source_wf_status || '*' }}</code>
          </template>
        </el-table-column>
        <el-table-column label="Target" min-width="180">
          <template #default="scope">
            <code>{{ scope.row.target_pool || '-' }} / {{ scope.row.target_wf_status || '-' }}</code>
          </template>
        </el-table-column>
        <el-table-column label="Enabled" width="120">
          <template #default="scope">
            <el-switch
              :model-value="scope.row.enabled"
              @change="(value: boolean) => updateRule(scope.row, { enabled: value })"
            />
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="110">
          <template #default="scope">
            <el-popconfirm title="Delete this rule?" @confirm="removeRule(scope.row.id)">
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
