import { ref } from 'vue'

const storageKey = 'triggertodo-theme'
const isDark = ref(false)
let initialized = false

function userTimeZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}

function hourInTimeZone(timeZone: string) {
  const hourPart = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hour: '2-digit',
    hour12: false,
  })
    .formatToParts(new Date())
    .find((part) => part.type === 'hour')?.value
  const hour = Number(hourPart)
  if (!Number.isFinite(hour)) return new Date().getHours()
  return hour === 24 ? 0 : hour
}

function shouldUseDarkMode() {
  const hour = hourInTimeZone(userTimeZone())
  return hour >= 18 || hour < 7
}

function applyTheme(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  document.documentElement.dataset.timezone = userTimeZone()
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}

function refreshTheme() {
  isDark.value = shouldUseDarkMode()
  applyTheme(isDark.value)
}

function initializeTheme() {
  if (initialized) return
  initialized = true
  localStorage.removeItem(storageKey)
  refreshTheme()
  window.setInterval(refreshTheme, 60 * 1000)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refreshTheme()
  })
  window.addEventListener('focus', refreshTheme)
}

export function useTheme() {
  initializeTheme()
  return { isDark }
}
