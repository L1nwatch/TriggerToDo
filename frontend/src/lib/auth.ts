import { reactive } from 'vue'

interface AuthState {
  loading: boolean
  ready: boolean
  authenticated: boolean
  name: string
  email: string
}

export const authState = reactive<AuthState>({
  loading: false,
  ready: false,
  authenticated: false,
  name: '',
  email: '',
})

export async function refreshAuth() {
  authState.loading = false
  authState.authenticated = true
  authState.name = ''
  authState.email = ''
  authState.ready = true
}
