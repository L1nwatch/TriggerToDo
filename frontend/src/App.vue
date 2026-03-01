<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { fetchAllTasks, listEpics } from './lib/api'
import { isOnOrAfterBoardCutoff } from './lib/boardCutoff'
import { hasAnyTriggerConfigured } from './lib/triggerSignal'

const route = useRoute()
const sidebarCounts = reactive({
  epics: 0,
  triggered: 0,
  waiting: 0,
})

const activePath = computed(() => {
  if (route.path.startsWith('/epics')) return '/epics'
  if (route.path.startsWith('/events')) return '/events'
  if (route.path.startsWith('/triggers') || route.path.startsWith('/settings')) return '/triggers'
  if (route.path.startsWith('/board/triggered')) return '/board/triggered'
  if (route.path.startsWith('/board/waiting-trigger')) return '/board/waiting-trigger'
  return '/board/triggered'
})

function isCompletedStatus(status?: string) {
  const value = (status || '').toLowerCase()
  return value.includes('done') || value.includes('closed') || value.includes('resolved') || value.includes('complete')
}

async function loadSidebarCounts() {
  try {
    const [data, epicsData] = await Promise.all([fetchAllTasks(), listEpics()])
    const openTasks = data.tasks.filter((task) => task.status !== 'completed' && isOnOrAfterBoardCutoff(task))
    sidebarCounts.epics = epicsData.items.filter((epic) => !isCompletedStatus(epic.status)).length
    sidebarCounts.triggered = openTasks.filter((task) => hasAnyTriggerConfigured(task)).length
    sidebarCounts.waiting = openTasks.length - sidebarCounts.triggered
  } catch {
    sidebarCounts.epics = 0
    sidebarCounts.triggered = 0
    sidebarCounts.waiting = 0
  }
}

onMounted(async () => {
  await loadSidebarCounts()
})

watch(
  () => route.fullPath,
  () => {
    loadSidebarCounts()
  },
)
</script>

<template>
  <div class="app-frame">
    <aside class="side-nav">
      <div class="brand-block">
        <p class="brand">TriggerToDo</p>
        <p class="brand-sub">Plan by trigger, execute with focus</p>
      </div>
      <el-menu :default-active="activePath" router class="menu">
        <el-menu-item index="/epics">
          <span class="menu-item-row">
            <span>Epics</span>
            <el-tag size="small" effect="dark" class="nav-count nav-count-epics">{{ sidebarCounts.epics }}</el-tag>
          </span>
        </el-menu-item>
        <el-menu-item index="/board/triggered">
          <span class="menu-item-row">
            <span>Trigger Set</span>
            <el-tag size="small" effect="dark" class="nav-count nav-count-triggered">{{ sidebarCounts.triggered }}</el-tag>
          </span>
        </el-menu-item>
        <el-menu-item index="/board/waiting-trigger">
          <span class="menu-item-row">
            <span>Trigger Missing</span>
            <el-tag size="small" effect="dark" class="nav-count nav-count-waiting">{{ sidebarCounts.waiting }}</el-tag>
          </span>
        </el-menu-item>
        <el-menu-item index="/triggers">Triggers</el-menu-item>
        <el-menu-item index="/events">Events</el-menu-item>
      </el-menu>
    </aside>

    <main class="content">
      <router-view />
    </main>
  </div>
</template>
