import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AgentSessionSidebar from '@/components/agent/AgentSessionSidebar.vue'
import AgentCenterPanel from '@/components/agent/AgentCenterPanel.vue'
import AgentBrowserPanel from '@/components/agent/AgentBrowserPanel.vue'
import { useAgentStore } from '@/stores/agent'
import { useAgentLayoutStore } from '@/stores/agentLayout'
import { createTestI18n } from '@/__tests__/helpers/i18n'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(async (url: string) => {
      if (url.includes('/api/ai/models')) {
        return { data: { models: [{ id: 'mimo-v1', provider: 'test', name: 'MiMo' }] } }
      }
      if (url.includes('/files')) {
        return { data: { files: [] } }
      }
      if (url.includes('/versions')) {
        return {
          data: {
            current_record_point: null,
            record_points: [],
            pending_changes_count: 2,
          },
        }
      }
      return { data: [] }
    }),
    post: vi.fn(async () => ({ data: {} })),
    put: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
  },
}))

function mountWithPinia(component: any, props: Record<string, unknown>) {
  return mount(component, {
    props,
    global: { plugins: [createPinia(), createTestI18n('zh-CN')] },
  })
}

describe('Agent workspace panels', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('sidebar renders a unique title and New Agent button', () => {
    const wrapper = mountWithPinia(AgentSessionSidebar, { projectId: 'p1', collapsed: false })
    expect(wrapper.text()).toContain('对话')
    expect(wrapper.find('[data-testid="agent-new-session"]').exists()).toBe(true)
  })

  it('sidebar lists sessions from the agent store', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const agentStore = useAgentStore()
    agentStore.sessions = [
      {
        session_id: 's1',
        project_id: 'p1',
        role: 'user',
        title: '第一章续写',
        status: 'completed',
        message_count: 0,
        archived_at: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]

    const wrapper = mount(AgentSessionSidebar, {
      props: { projectId: 'p1', collapsed: false },
      global: { plugins: [pinia, createTestI18n('zh-CN')] },
    })

    expect(wrapper.find('[data-testid="agent-session-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-session-item-s1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('第一章续写')
  })

  it('sidebar collapses and expands', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const layoutStore = useAgentLayoutStore()

    const wrapper = mount(AgentSessionSidebar, {
      props: {
        projectId: 'p1',
        collapsed: layoutStore.sidebarCollapsed,
        'onUpdate:collapsed': (value: boolean) => layoutStore.setSidebarCollapsed(value),
      },
      global: { plugins: [pinia, createTestI18n('zh-CN')] },
    })

    await wrapper.find('[data-testid="agent-sidebar-collapse"]').trigger('click')
    expect(layoutStore.sidebarCollapsed).toBe(true)

    await wrapper.setProps({ collapsed: true })
    await wrapper.find('[data-testid="agent-sidebar-expand"]').trigger('click')
    expect(layoutStore.sidebarCollapsed).toBe(false)
  })

  it('center panel exposes chat input, send button and a single model select', () => {
    const wrapper = mountWithPinia(AgentCenterPanel, { projectId: 'p1' })
    expect(wrapper.find('[data-testid="agent-chat-input"]').exists()).toBe(true)
    const sendButton = wrapper.find('[data-testid="agent-send-button"]')
    expect(sendButton.exists()).toBe(true)
    expect(sendButton.attributes('aria-label')).toBe('发送')
    expect(wrapper.find('[data-testid="agent-model-select"]').exists()).toBe(true)
    expect(wrapper.findAll('select')).toHaveLength(0)
    expect(sendButton.attributes('aria-label')).not.toMatch(/对话|图谱/i)
  })

  it('browser panel shows pinned editor and versions tabs by default', async () => {
    const wrapper = mountWithPinia(AgentBrowserPanel, { projectId: 'p1' })
    expect(wrapper.findAll('select')).toHaveLength(0)
    const activityBar = wrapper.find('[data-testid="agent-activity-bar"]')
    expect(activityBar.exists()).toBe(true)
    expect(activityBar.classes()).toContain('muse-activity-bar-top')
    expect(wrapper.find('[data-testid="agent-activity-editor"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-activity-versions"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-activity-graph"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="agent-activity-entities"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="agent-activity-memory"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="agent-activity-add"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-file-explorer"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-editor-pane"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-browser-tab"]').exists()).toBe(false)
  })

  it('browser panel opens and closes optional panels like Cursor', async () => {
    const wrapper = mountWithPinia(AgentBrowserPanel, { projectId: 'p1' })
    await wrapper.find('[data-testid="agent-activity-add"]').trigger('click')
    await wrapper.find('[data-testid="agent-activity-picker-entities"]').trigger('click')
    expect(wrapper.find('[data-testid="agent-activity-entities"]').exists()).toBe(true)
    await wrapper.find('[data-testid="agent-activity-entities"]').trigger('click')
    expect(wrapper.find('[data-testid="agent-entities-panel"]').exists()).toBe(true)

    await wrapper.find('[data-testid="agent-activity-close-entities"]').trigger('click')
    expect(wrapper.find('[data-testid="agent-activity-entities"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="agent-activity-editor"]').exists()).toBe(true)
  })
})
