import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/board/triggered' },
    { path: '/today', redirect: '/board/triggered' },
    { path: '/epics', name: 'epics', component: () => import('./pages/EpicPage.vue') },
    { path: '/board', redirect: '/board/triggered' },
    {
      path: '/board/:pool',
      name: 'board',
      component: () => import('./pages/BoardPage.vue'),
    },
    {
      path: '/triggers',
      name: 'triggers',
      component: () => import('./pages/TriggerManagementPage.vue'),
    },
    {
      path: '/events',
      name: 'events',
      component: () => import('./pages/EventManagementPage.vue'),
    },
    {
      path: '/tasks/:listId/:taskId',
      name: 'task-detail',
      component: () => import('./pages/TaskDetailPage.vue'),
    },
    {
      path: '/settings',
      redirect: '/triggers',
    },
  ],
})

export default router
