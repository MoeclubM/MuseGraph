import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentFileExplorer from '@/components/agent/AgentFileExplorer.vue'
import { createTestI18n } from '@/__tests__/helpers/i18n'

const baseProps = {
  chapters: [
    {
      id: 'ch-1',
      project_id: 'p1',
      title: '第一章',
      content: 'hello',
      order_index: 0,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
  ],
  files: [
    {
      path: 'notes/readme.md',
      name: 'readme.md',
      size: 12,
      content_type: 'text/markdown',
      modified_at: '2024-01-01T00:00:00Z',
      text_extractable: true,
    },
  ],
  filesLoading: false,
  activeKind: null,
  activeChapterId: '',
  activeFilePath: '',
  searchQuery: '',
  chapterImporting: false,
  chapterImportMessage: null,
  canDeleteChapter: true,
  inlineRenameChapterId: '',
  inlineRenameChapterTitle: '',
  inlineRenameFilePath: '',
  inlineRenameFileName: '',
  inlineRenameSubmitting: false,
  chapterAccept: '.txt,.md',
}

describe('AgentFileExplorer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('emits deleteChapterById from chapter context menu', async () => {
    const wrapper = mount(AgentFileExplorer, {
      props: baseProps,
      global: { plugins: [createTestI18n('zh-CN')] },
      attachTo: document.body,
    })

    await wrapper.find('[data-testid="agent-explorer-chapter-item"]').trigger('contextmenu')
    const menu = document.querySelector('[data-testid="agent-explorer-context-delete"]') as HTMLElement
    expect(menu).toBeTruthy()
    menu.click()

    expect(wrapper.emitted('deleteChapterById')).toEqual([['ch-1']])
    wrapper.unmount()
  })

  it('emits deleteFile from file context menu', async () => {
    const wrapper = mount(AgentFileExplorer, {
      props: baseProps,
      global: { plugins: [createTestI18n('zh-CN')] },
      attachTo: document.body,
    })

    await wrapper.find('[data-testid="agent-explorer-file-item"]').trigger('contextmenu')
    const menu = document.querySelector('[data-testid="agent-explorer-context-delete"]') as HTMLElement
    expect(menu).toBeTruthy()
    menu.click()

    expect(wrapper.emitted('deleteFile')).toEqual([['notes/readme.md']])
    wrapper.unmount()
  })
})
