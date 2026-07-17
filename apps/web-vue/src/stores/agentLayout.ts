import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type ColumnId = 'sessions' | 'center' | 'browser'
export type BrowserPanelId = 'editor' | 'graph' | 'entities' | 'versions' | 'memory' | 'subagents'

export const PINNED_BROWSER_PANELS: BrowserPanelId[] = ['editor', 'versions']
export const OPTIONAL_BROWSER_PANELS: BrowserPanelId[] = ['graph', 'entities', 'memory', 'subagents']

const VISIBILITY_KEY = 'musegraph-agent-panel-visibility'
const LAYOUT_KEY_PREFIX = 'musegraph-agent-layout-'
const SIDEBAR_COLLAPSED_KEY = 'musegraph-agent-sidebar-collapsed'
const SIDEBAR_WIDTH_KEY = 'musegraph-agent-sidebar-width'
export const SIDEBAR_MIN_WIDTH = 160
export const SIDEBAR_MAX_WIDTH = 420
const DEFAULT_SIDEBAR_WIDTH = 208
const SIDEBAR_COLLAPSED_WIDTH = 48

export const CENTER_PANEL_MIN_WIDTH = 72
export const BROWSER_MIN_WIDTH = 300
const DEFAULT_BROWSER_WIDTH = 480

interface StoredLayout {
  browserWidth: number
  sidebarWidth?: number
}

interface StoredVisibility {
  openOptionalPanels: BrowserPanelId[]
}

function isOptionalBrowserPanelId(value: unknown): value is BrowserPanelId {
  return typeof value === 'string' && OPTIONAL_BROWSER_PANELS.includes(value as BrowserPanelId)
}

function normalizeOptionalPanels(order: unknown): BrowserPanelId[] {
  if (!Array.isArray(order)) return []
  const seen = new Set<BrowserPanelId>()
  const next: BrowserPanelId[] = []
  for (const item of order) {
    if (!isOptionalBrowserPanelId(item) || seen.has(item)) continue
    seen.add(item)
    next.push(item)
  }
  return next
}

function loadVisibility(): StoredVisibility {
  try {
    const raw = localStorage.getItem(VISIBILITY_KEY)
    if (!raw) return { openOptionalPanels: [] }
    const parsed = JSON.parse(raw) as Partial<StoredVisibility>
    return { openOptionalPanels: normalizeOptionalPanels(parsed.openOptionalPanels) }
  } catch {
    return { openOptionalPanels: [] }
  }
}


function loadSidebarWidth(): number {
  try {
    const raw = localStorage.getItem(SIDEBAR_WIDTH_KEY)
    const n = Number(raw)
    if (!Number.isFinite(n)) return DEFAULT_SIDEBAR_WIDTH
    return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(n)))
  } catch {
    return DEFAULT_SIDEBAR_WIDTH
  }
}

function clampSidebarWidth(value: number): number {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(value)))
}

function loadLayout(projectId: string): StoredLayout {
  const fallback: StoredLayout = { browserWidth: DEFAULT_BROWSER_WIDTH, sidebarWidth: loadSidebarWidth() }
  if (!projectId) return fallback
  try {
    const raw = localStorage.getItem(LAYOUT_KEY_PREFIX + projectId)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<StoredLayout>
    return {
      browserWidth: clampBrowserWidth(Number(parsed.browserWidth) || DEFAULT_BROWSER_WIDTH),
      sidebarWidth: clampSidebarWidth(Number(parsed.sidebarWidth) || loadSidebarWidth()),
    }
  } catch {
    return fallback
  }
}

function loadSidebarCollapsed(): boolean {
  try {
    const raw = localStorage.getItem(SIDEBAR_COLLAPSED_KEY)
    if (!raw) return false
    return JSON.parse(raw) === true
  } catch {
    return false
  }
}

function clampBrowserWidth(value: number): number {
  return Math.min(960, Math.max(BROWSER_MIN_WIDTH, Math.round(value)))
}

export const useAgentLayoutStore = defineStore('agentLayout', () => {
  const projectId = ref('')
  const browserWidth = ref(DEFAULT_BROWSER_WIDTH)
  const openOptionalPanels = ref<BrowserPanelId[]>([])
  const sidebarCollapsed = ref(loadSidebarCollapsed())
  const sidebarWidth = ref(loadSidebarWidth())
  const isColumnResizing = ref(false)

  const activityBarPanels = computed(() => [
    ...PINNED_BROWSER_PANELS,
    ...openOptionalPanels.value,
  ])

  const availableOptionalPanels = computed(() =>
    OPTIONAL_BROWSER_PANELS.filter((id) => !openOptionalPanels.value.includes(id))
  )

  function bindProject(id: string) {
    if (projectId.value === id) return
    projectId.value = id
    const layout = loadLayout(id)
    browserWidth.value = layout.browserWidth
    sidebarWidth.value = layout.sidebarWidth ?? loadSidebarWidth()
  }

  function persistLayout() {
    if (!projectId.value) return
    const payload: StoredLayout = { browserWidth: browserWidth.value, sidebarWidth: sidebarWidth.value }
    localStorage.setItem(LAYOUT_KEY_PREFIX + projectId.value, JSON.stringify(payload))
  }

  function persistVisibility() {
    const payload: StoredVisibility = { openOptionalPanels: openOptionalPanels.value }
    localStorage.setItem(VISIBILITY_KEY, JSON.stringify(payload))
  }

  function initVisibility() {
    openOptionalPanels.value = loadVisibility().openOptionalPanels
  }

  function setBrowserWidth(width: number, options?: { persist?: boolean }) {
    browserWidth.value = clampBrowserWidth(width)
    if (options?.persist !== false && !isColumnResizing.value) persistLayout()
  }

  function setSidebarWidth(width: number, options?: { persist?: boolean }) {
    sidebarWidth.value = clampSidebarWidth(width)
    const shouldPersist = options?.persist !== false && !isColumnResizing.value
    if (shouldPersist) {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth.value))
      if (projectId.value) persistLayout()
    }
  }

  function beginColumnResize() {
    isColumnResizing.value = true
  }

  function endColumnResize() {
    isColumnResizing.value = false
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth.value))
    if (projectId.value) {
      const payload: StoredLayout = { browserWidth: browserWidth.value, sidebarWidth: sidebarWidth.value }
      localStorage.setItem(LAYOUT_KEY_PREFIX + projectId.value, JSON.stringify(payload))
    }
  }

  function resizeSidebar(deltaX: number) {
    if (sidebarCollapsed.value) return
    setSidebarWidth(sidebarWidth.value + deltaX, { persist: false })
  }

  function resizeBrowser(deltaX: number) {
    setBrowserWidth(browserWidth.value - deltaX, { persist: false })
  }

  function sidebarWidthStyle(): string {
    return sidebarCollapsed.value ? `${SIDEBAR_COLLAPSED_WIDTH}px` : `${sidebarWidth.value}px`
  }

  function setSidebarCollapsed(collapsed: boolean) {
    sidebarCollapsed.value = collapsed
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, JSON.stringify(collapsed))
  }

  function toggleSidebarCollapsed() {
    setSidebarCollapsed(!sidebarCollapsed.value)
  }

  function isBrowserPanelPinned(panelId: BrowserPanelId): boolean {
    return PINNED_BROWSER_PANELS.includes(panelId)
  }

  function isBrowserPanelOpen(panelId: BrowserPanelId): boolean {
    if (isBrowserPanelPinned(panelId)) return true
    return openOptionalPanels.value.includes(panelId)
  }

  function openBrowserPanel(panelId: BrowserPanelId) {
    if (isBrowserPanelPinned(panelId) || openOptionalPanels.value.includes(panelId)) return
    if (!OPTIONAL_BROWSER_PANELS.includes(panelId)) return
    openOptionalPanels.value = [...openOptionalPanels.value, panelId]
    persistVisibility()
  }

  function closeBrowserPanel(panelId: BrowserPanelId) {
    if (isBrowserPanelPinned(panelId)) return
    openOptionalPanels.value = openOptionalPanels.value.filter((id) => id !== panelId)
    persistVisibility()
  }

  function browserWidthStyle(): string {
    return `${browserWidth.value}px`
  }

  initVisibility()

  return {
    projectId,
    browserWidth,
    openOptionalPanels,
    sidebarCollapsed,
    sidebarWidth,
    activityBarPanels,
    availableOptionalPanels,
    bindProject,
    setBrowserWidth,
    resizeBrowser,
    isColumnResizing,
    beginColumnResize,
    endColumnResize,
    resizeSidebar,
    setSidebarWidth,
    sidebarWidthStyle,
    setSidebarCollapsed,
    toggleSidebarCollapsed,
    isBrowserPanelPinned,
    isBrowserPanelOpen,
    openBrowserPanel,
    closeBrowserPanel,
    browserWidthStyle,
  }
})
