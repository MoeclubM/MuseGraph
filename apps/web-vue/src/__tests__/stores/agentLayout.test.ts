import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  OPTIONAL_BROWSER_PANELS,
  PINNED_BROWSER_PANELS,
  useAgentLayoutStore,
} from '@/stores/agentLayout'

describe('agentLayout store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('loads and persists per-project browser width', () => {
    const store = useAgentLayoutStore()
    store.bindProject('project-a')
    store.setBrowserWidth(500)

    const raw = localStorage.getItem('musegraph-agent-layout-project-a')
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!)).toMatchObject({
      browserWidth: 500,
    })

    const next = useAgentLayoutStore()
    next.bindProject('project-a')
    expect(next.browserWidth).toBe(500)
  })

  it('keeps pinned panels always open and optional panels on demand', () => {
    const store = useAgentLayoutStore()
    expect(store.activityBarPanels).toEqual(PINNED_BROWSER_PANELS)
    expect(PINNED_BROWSER_PANELS.every((id) => store.isBrowserPanelOpen(id))).toBe(true)

    store.openBrowserPanel('graph')
    expect(store.activityBarPanels).toEqual([...PINNED_BROWSER_PANELS, 'graph'])
    expect(store.isBrowserPanelOpen('graph')).toBe(true)

    store.closeBrowserPanel('graph')
    expect(store.activityBarPanels).toEqual(PINNED_BROWSER_PANELS)
    store.closeBrowserPanel('editor')
    expect(store.activityBarPanels).toEqual(PINNED_BROWSER_PANELS)
  })

  it('persists optional panel state globally', () => {
    const store = useAgentLayoutStore()
    store.openBrowserPanel('memory')
    store.openBrowserPanel('entities')

    const raw = localStorage.getItem('musegraph-agent-panel-visibility')
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).openOptionalPanels).toEqual(['memory', 'entities'])

    const next = useAgentLayoutStore()
    expect(next.openOptionalPanels).toEqual(['memory', 'entities'])
    expect(next.availableOptionalPanels).toEqual(
      OPTIONAL_BROWSER_PANELS.filter((id) => id !== 'memory' && id !== 'entities')
    )
  })

  it('persists sidebar collapsed state', () => {
    const store = useAgentLayoutStore()
    expect(store.sidebarCollapsed).toBe(false)

    store.setSidebarCollapsed(true)
    expect(localStorage.getItem('musegraph-agent-sidebar-collapsed')).toBe('true')

    const next = useAgentLayoutStore()
    expect(next.sidebarCollapsed).toBe(true)

    next.toggleSidebarCollapsed()
    expect(next.sidebarCollapsed).toBe(false)
  })

  it('resizes browser panel width via resizeBrowser', () => {
    const store = useAgentLayoutStore()
    store.bindProject('project-b')
    const initial = store.browserWidth
    store.resizeBrowser(-40)
    expect(store.browserWidth).toBe(initial + 40)
  })
})
