import { ref, watch } from 'vue'

const storageKey = 'triggertodo-theme'
const isDark = ref(false)
let initialized = false

function systemPrefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

function savedTheme() {
  const value = localStorage.getItem(storageKey)
  return value === 'dark' || value === 'light' ? value : null
}

function applyTheme(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  localStorage.setItem(storageKey, dark ? 'dark' : 'light')
}

function initializeTheme() {
  if (initialized) return
  initialized = true
  const saved = savedTheme()
  isDark.value = saved === 'dark' || (!saved && systemPrefersDark())
  applyTheme(isDark.value)
  watch(isDark, applyTheme, { flush: 'sync' })
}

export function useTheme() {
  initializeTheme()
  return { isDark }
}
