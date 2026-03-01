<script setup lang="ts">
import { ref } from 'vue'

const loading = ref(false)

function login() {
  loading.value = true
  window.location.assign('/api/auth/login')
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <p class="eyebrow">TriggerToDo</p>
      <h1>Sign in to continue</h1>
      <p class="subtitle">This app uses a local cookie session and local DB data.</p>
      <el-button type="primary" :loading="loading" size="large" @click="login">Continue</el-button>
    </div>
  </div>
</template>
