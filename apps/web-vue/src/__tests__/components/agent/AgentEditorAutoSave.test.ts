import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AgentBrowserPanel from '@/components/agent/AgentBrowserPanel.vue'
import AgentEditorPane from '@/components/agent/AgentEditorPane.vue'
import { createTestI18n } from '@/__tests__/helpers/i18n'
import { useProjectStore } from '@/stores/project'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(async (url: string) => {
      if (url.includes('/files')) {
        return { data: { files: [] } }
      }
      return { data: [] }
    }),
    post: vi.fn(async () => ({ data: {} })),
    put: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
  },
}))

describe('Agent editor auto-save', () => {
  let pinia: ReturnType<typeof createPinia>

  beforeEach(() => {
    vi.useFakeTimers()
    pinia = createPinia()
    setActivePinia(pinia)
    const projectStore = useProjectStore()
    projectStore.currentProject = {
      id: 'p1',
      title: 'Test',
      chapters: [{ id: 'c1', title: 'Ch1', content: 'hello', order_index: 0, status: 'draft' }],
    } as any
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces chapter saves without a manual save button', async () => {
    const updateChapter = vi.spyOn(useProjectStore(), 'updateChapter').mockResolvedValue([] as any)

    const wrapper = mount(AgentBrowserPanel, {
      props: { projectId: 'p1' },
      global: { plugins: [pinia, createTestI18n('zh-CN')] },
    })

    await flushPromises()
    expect(wrapper.find('[data-testid="agent-editor-save"]').exists()).toBe(false)

    const pane = wrapper.findComponent(AgentEditorPane)
    expect(pane.exists()).toBe(true)
    await pane.vm.$emit('update:modelValue', 'hello world')
    expect(updateChapter).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(800)
    await flushPromises()
    expect(updateChapter).toHaveBeenCalledWith('p1', 'c1', { content: 'hello world' })
  })
})
