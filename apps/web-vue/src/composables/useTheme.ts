import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'musegraph.theme.mode'
const themeMode = ref<ThemeMode>('system')
const systemDark = ref(false)

let mediaQuery: MediaQueryList | null = null
let listenerBound = false

function resolveMode(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') {
    return systemDark.value ? 'dark' : 'light'
  }
  return mode
}

function applyThemeClass() {
  if (typeof document === 'undefined') return
  const resolved = resolveMode(themeMode.value)
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.setAttribute('data-theme', resolved)
}

function handleSystemThemeChange(event: MediaQueryListEvent) {
  systemDark.value = event.matches
  if (themeMode.value === 'system') {
    applyThemeClass()
  }
}

export function initTheme() {
  if (typeof window === 'undefined') return
  if (!mediaQuery) {
    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  }
  systemDark.value = mediaQuery.matches

  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    themeMode.value = stored
  } else {
    themeMode.value = 'system'
  }

  if (!listenerBound) {
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleSystemThemeChange)
    } else {
      mediaQuery.addListener(handleSystemThemeChange)
    }
    listenerBound = true
  }

  applyThemeClass()
}

export function useTheme() {
  const resolvedTheme = computed(() => resolveMode(themeMode.value))

  function setTheme(mode: ThemeMode) {
    themeMode.value = mode
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, mode)
    }
    applyThemeClass()
  }

  return {
    themeMode,
    resolvedTheme,
    setTheme,
  }
}
