import { computed, ref } from 'vue'
import { palettes, type PaletteId } from './palettes'

export type ThemeMode = 'light' | 'dark' | 'system'

const THEME_KEY = 'musegraph.theme.mode'
const PALETTE_KEY = 'musegraph.theme.palette'
const themeMode = ref<ThemeMode>('system')
const paletteId = ref<PaletteId>('amber')
const systemDark = ref(false)

let mediaQuery: MediaQueryList | null = null
let listenerBound = false

function resolveMode(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') {
    return systemDark.value ? 'dark' : 'light'
  }
  return mode
}

function applyPalette() {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const resolved = resolveMode(themeMode.value)
  const palette = palettes[paletteId.value]
  const vars = resolved === 'dark' ? palette.dark : palette.light
  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value)
  }
}

function applyThemeClass() {
  if (typeof document === 'undefined') return
  const resolved = resolveMode(themeMode.value)
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.setAttribute('data-theme', resolved)
  applyPalette()
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

  const storedMode = window.localStorage.getItem(THEME_KEY)
  if (storedMode === 'light' || storedMode === 'dark' || storedMode === 'system') {
    themeMode.value = storedMode
  } else {
    themeMode.value = 'system'
  }

  const storedPalette = window.localStorage.getItem(PALETTE_KEY) as PaletteId | null
  if (storedPalette && palettes[storedPalette]) {
    paletteId.value = storedPalette
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
      window.localStorage.setItem(THEME_KEY, mode)
    }
    applyThemeClass()
  }

  function setPalette(id: PaletteId) {
    paletteId.value = id
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(PALETTE_KEY, id)
    }
    applyPalette()
  }

  return {
    themeMode,
    resolvedTheme,
    setTheme,
    paletteId,
    setPalette,
  }
}
