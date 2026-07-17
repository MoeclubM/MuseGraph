<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Boxes, Database, FileText, GitBranch, Plus, Share2, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { useAgentStore } from '@/stores/agent'
import {
  OPTIONAL_BROWSER_PANELS,
  useAgentLayoutStore,
  type BrowserPanelId,
} from '@/stores/agentLayout'
import { getProjectVersionHistory } from '@/api/projectVersions'
import { useProjectStore } from '@/stores/project'
import { useToast } from '@/composables/useToast'
import { getMemoryVisualization } from '@/api/memory'
import {
  deleteProjectFile,
  listProjectFiles,
  readProjectFile,
  renameProjectFile,
} from '@/api/projectFiles'
import type { ProjectFile } from '@/api/projectFiles'
import AgentFileExplorer from '@/components/agent/AgentFileExplorer.vue'
import AgentEditorPane from '@/components/agent/AgentEditorPane.vue'
import Modal from '@/components/ui/Modal.vue'
import Button from '@/components/ui/Button.vue'
import AgentVersionsPanel from '@/components/agent/AgentVersionsPanel.vue'
import GraphPanel from '@/components/graph/GraphPanel.vue'
import AgentEntitiesPanel from '@/components/agent/AgentEntitiesPanel.vue'
import AgentMemoryPanel from '@/components/agent/AgentMemoryPanel.vue'
import type {
  AgentWorkspace,
  GraphData,
  ProjectChapter,
} from '@/types'

type EditorKind = 'chapter' | 'file'

const props = defineProps<{
  projectId: string
}>()

const AUTO_SAVE_MS = 800

const { t } = useI18n()
const agentStore = useAgentStore()
const layoutStore = useAgentLayoutStore()
const projectStore = useProjectStore()
const toast = useToast()

const activePanel = ref<BrowserPanelId>('editor')
const graphOpened = ref(false)
const entitiesOpened = ref(false)
const panelPickerOpen = ref(false)
const pendingGitChanges = ref(0)
const entitiesPanelRef = ref<InstanceType<typeof AgentEntitiesPanel> | null>(null)

const panelMeta: Partial<Record<
  BrowserPanelId,
  { icon: typeof FileText; label: () => string }
>> = {
  editor: { icon: FileText, label: () => t('agent.browser.panels.editor') },
  graph: { icon: Share2, label: () => t('agent.browser.panels.graph') },
  memory: { icon: Database, label: () => t('agent.browser.panels.memory') },
  entities: { icon: Boxes, label: () => t('agent.browser.panels.entities') },
  versions: { icon: GitBranch, label: () => t('agent.browser.panels.versions') },
  subagents: { icon: Boxes, label: () => t('agent.browser.panels.entities') },
}

const activityBarTabs = computed(() =>
  layoutStore.activityBarPanels
    .map((id) => {
      const meta = panelMeta[id]
      if (!meta) return null
      return {
        id,
        icon: meta.icon,
        label: meta.label(),
        pinned: layoutStore.isBrowserPanelPinned(id),
      }
    })
    .filter((tab): tab is NonNullable<typeof tab> => tab !== null)
)

const availableOptionalPanels = computed(() =>
  OPTIONAL_BROWSER_PANELS.filter((id) => !layoutStore.isBrowserPanelOpen(id)).map((id) => ({
    id,
    label: panelMeta[id]?.label() ?? id,
  }))
)

// ---- workspace data ----

const workspace = computed<AgentWorkspace>(() => {
  return (
    agentStore.currentSession?.agent_workspace
    || projectStore.currentProject?.creative_state?.agent_workspace
    || {}
  )
})

const memoryGraph = ref<GraphData>({ nodes: [], edges: [] })
const memoryGraphLoading = ref(false)
const memoryGraphError = ref<string | null>(null)

function normalizeGraphInput(graph: Record<string, unknown> | null | undefined): GraphData {
  const rawNodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const rawEdges = Array.isArray(graph?.edges) ? graph.edges : []
  const nodes = rawNodes.map((node, index) => {
    const row = node as Record<string, unknown>
    const id = String(row.id ?? row.name ?? `node-${index}`)
    return {
      ...row,
      id,
      label: String(row.label ?? row.name ?? row.id ?? id),
      type: String(row.type ?? row.kind ?? 'Entity'),
    }
  })
  const ids = new Set(nodes.map((node) => node.id))
  const edges = rawEdges
    .map((edge) => {
      const row = edge as Record<string, unknown>
      return {
        ...row,
        source: String(row.source ?? row.from ?? row.source_id ?? row.src ?? ''),
        target: String(row.target ?? row.to ?? row.target_id ?? row.dst ?? ''),
        label: String(row.label ?? row.relation ?? row.type ?? ''),
      }
    })
    .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
  return { nodes, edges }
}

function mergeGraphData(primary: GraphData, secondary: GraphData): GraphData {
  const nodeMap = new Map(primary.nodes.map((node) => [node.id, node]))
  for (const node of secondary.nodes) {
    if (!nodeMap.has(node.id)) nodeMap.set(node.id, node)
  }
  const edgeMap = new Map<string, GraphData['edges'][number]>()
  for (const edge of [...primary.edges, ...secondary.edges]) {
    const key = `${edge.source}->${edge.target}:${edge.label || edge.type || ''}`
    if (!edgeMap.has(key)) edgeMap.set(key, edge)
  }
  return { nodes: [...nodeMap.values()], edges: [...edgeMap.values()] }
}

const workspaceGraphData = computed<GraphData>(() =>
  normalizeGraphInput(workspace.value.graph as Record<string, unknown> | undefined)
)

const graphData = computed<GraphData>(() => mergeGraphData(workspaceGraphData.value, memoryGraph.value))

async function loadMemoryGraph() {
  if (!props.projectId) return
  memoryGraphLoading.value = true
  memoryGraphError.value = null
  try {
    memoryGraph.value = normalizeGraphInput(
      (await getMemoryVisualization(props.projectId)) as unknown as Record<string, unknown>
    )
  } catch (error) {
    memoryGraph.value = { nodes: [], edges: [] }
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    memoryGraphError.value =
      detail || (error instanceof Error ? error.message : t('agent.browser.loadMemoryGraphFailed'))
  } finally {
    memoryGraphLoading.value = false
  }
}

// ---- Editor: chapters + project files ----

const CHAPTER_ACCEPT = '.txt,.md,.markdown'

const editorKind = ref<EditorKind | null>(null)
const activeChapterId = ref('')
const activeFilePath = ref('')
const editorDraft = ref('')
const editorBaseline = ref('')
const explorerSearchQuery = ref('')
const chapterImporting = ref(false)
const chapterImportMessage = ref<string | null>(null)
const inlineRenameChapterId = ref('')
const inlineRenameChapterTitle = ref('')
const inlineRenameFilePath = ref('')
const inlineRenameFileName = ref('')
const inlineRenameSubmitting = ref(false)
const deleteConfirmOpen = ref(false)
const deleteConfirmSubmitting = ref(false)
const deleteConfirmKind = ref<'chapter' | 'file'>('chapter')
const deleteConfirmChapterId = ref('')
const deleteConfirmFilePath = ref('')
const deleteConfirmLabel = ref('')
const projectFiles = ref<ProjectFile[]>([])
const projectFilesLoading = ref(false)
const fileLoading = ref(false)
const editorLoaded = ref(false)

const orderedChapters = computed(() => projectStore.orderedChapters)

const activeChapter = computed<ProjectChapter | null>(
  () => orderedChapters.value.find((chapter) => chapter.id === activeChapterId.value) || null
)

const activeFile = computed(
  () => projectFiles.value.find((file) => file.path === activeFilePath.value) || null
)

const editorDirty = computed(
  () => editorKind.value === 'chapter' && editorDraft.value !== editorBaseline.value
)

const versionChangeCount = computed(() => {
  let count = pendingGitChanges.value
  if (editorDirty.value) count += 1
  return count
})

const versionChangeLabel = computed(() => {
  if (!versionChangeCount.value) return ''
  if (editorDirty.value && pendingGitChanges.value > 0) {
    return t('agent.browser.versionChangeMixed', { count: pendingGitChanges.value })
  }
  if (editorDirty.value) return t('agent.browser.versionChangeUnsaved')
  return t('agent.browser.versionChangeCount', { count: pendingGitChanges.value })
})

const editorReadOnly = computed(() => editorKind.value === 'file')
const editorSaving = computed(() => projectStore.chapterSaving)

const editorTitle = computed(() => {
  if (editorKind.value === 'chapter') {
    return activeChapter.value?.title || ''
  }
  if (editorKind.value === 'file') {
    return activeFile.value?.name || activeFilePath.value
  }
  return ''
})

const editorBreadcrumb = computed(() => {
  const projectTitle = projectStore.currentProject?.title || t('agent.editor.breadcrumbProject')
  if (editorKind.value === 'chapter' && activeChapter.value) {
    return `${projectTitle} / ${t('agent.editor.explorerChapters')}`
  }
  if (editorKind.value === 'file' && activeFilePath.value) {
    const parts = activeFilePath.value.split('/')
    return `${projectTitle} / ${parts.slice(0, -1).join('/') || t('agent.editor.explorerFiles')}`
  }
  return projectTitle
})

const hasEditorSelection = computed(
  () =>
    (editorKind.value === 'chapter' && Boolean(activeChapter.value))
    || (editorKind.value === 'file' && Boolean(activeFilePath.value))
)

watch(
  orderedChapters,
  () => {
    if (editorKind.value !== 'chapter') return
    if (!activeChapterId.value || !orderedChapters.value.some((c) => c.id === activeChapterId.value)) {
      const first = orderedChapters.value[0]
      if (first) {
        selectChapter(first.id)
      } else {
        editorKind.value = null
        activeChapterId.value = ''
        editorDraft.value = ''
        editorBaseline.value = ''
      }
    }
  },
  { immediate: true }
)

async function loadProjectFiles() {
  if (!props.projectId) return
  projectFilesLoading.value = true
  try {
    projectFiles.value = await listProjectFiles(props.projectId)
  } catch {
    projectFiles.value = []
  } finally {
    projectFilesLoading.value = false
  }
}

function selectChapter(chapterId: string) {
  if (editorKind.value === 'chapter' && chapterId === activeChapterId.value) return
  editorKind.value = 'chapter'
  activeChapterId.value = chapterId
  activeFilePath.value = ''
  const chapter = orderedChapters.value.find((c) => c.id === chapterId)
  const content = chapter ? chapter.content || '' : ''
  editorDraft.value = content
  editorBaseline.value = content
}

async function selectFile(path: string) {
  if (editorKind.value === 'file' && path === activeFilePath.value && !fileLoading.value) return
  editorKind.value = 'file'
  activeFilePath.value = path
  activeChapterId.value = ''
  fileLoading.value = true
  try {
    const file = await readProjectFile(props.projectId, path)
    editorDraft.value = file.content
    editorBaseline.value = file.content
  } catch {
    editorDraft.value = ''
    editorBaseline.value = ''
    toast.error(t('agent.editor.loadFileFailed'))
  } finally {
    fileLoading.value = false
  }
}

async function saveActiveEditor() {
  if (!activeChapter.value || !editorDirty.value) return
  await projectStore.updateChapter(props.projectId, activeChapter.value.id, {
    content: editorDraft.value,
  })
  editorBaseline.value = editorDraft.value
  void refreshVersionChanges()
}

async function refreshVersionChanges() {
  if (!props.projectId) return
  try {
    const history = await getProjectVersionHistory(props.projectId)
    pendingGitChanges.value = history.pending_changes_count ?? 0
  } catch {
    pendingGitChanges.value = 0
  }
}

async function handleCreateChapter() {
  const chapters = await projectStore.createChapter(props.projectId, {})
  const last = chapters[chapters.length - 1]
  if (last) selectChapter(last.id)
}

function chapterDisplayName(chapter: ProjectChapter): string {
  return chapter.title || t('agent.editor.chapterFallback', { index: chapter.order_index + 1 })
}

function openDeleteChapterConfirm(chapterId: string) {
  const chapter = orderedChapters.value.find((item) => item.id === chapterId)
  if (!chapter) return
  deleteConfirmKind.value = 'chapter'
  deleteConfirmChapterId.value = chapterId
  deleteConfirmFilePath.value = ''
  deleteConfirmLabel.value = chapterDisplayName(chapter)
  deleteConfirmOpen.value = true
}

function openDeleteFileConfirm(path: string) {
  const file = projectFiles.value.find((item) => item.path === path)
  deleteConfirmKind.value = 'file'
  deleteConfirmChapterId.value = ''
  deleteConfirmFilePath.value = path
  deleteConfirmLabel.value = file?.name || path
  deleteConfirmOpen.value = true
}

function closeDeleteConfirm() {
  if (deleteConfirmSubmitting.value) return
  deleteConfirmOpen.value = false
  deleteConfirmChapterId.value = ''
  deleteConfirmFilePath.value = ''
  deleteConfirmLabel.value = ''
}

function handleDeleteActiveChapter() {
  if (!activeChapter.value) return
  openDeleteChapterConfirm(activeChapter.value.id)
}

function handleDeleteChapterById(chapterId: string) {
  openDeleteChapterConfirm(chapterId)
}

function handleDeleteFile(path: string) {
  openDeleteFileConfirm(path)
}

function clearEditorSelection() {
  editorKind.value = null
  activeChapterId.value = ''
  activeFilePath.value = ''
  editorDraft.value = ''
  editorBaseline.value = ''
}

async function confirmDelete() {
  if (deleteConfirmSubmitting.value) return
  deleteConfirmSubmitting.value = true
  try {
    if (deleteConfirmKind.value === 'chapter') {
      const chapterId = deleteConfirmChapterId.value
      if (!chapterId) return
      await projectStore.deleteChapter(props.projectId, chapterId)
      if (inlineRenameChapterId.value === chapterId) {
        cancelInlineRename()
      }
      if (editorKind.value === 'chapter' && activeChapterId.value === chapterId) {
        clearEditorSelection()
      }
      toast.success(t('agent.editor.deleteChapterSuccess'))
    } else {
      const path = deleteConfirmFilePath.value
      if (!path) return
      await deleteProjectFile(props.projectId, path)
      await loadProjectFiles()
      if (editorKind.value === 'file' && activeFilePath.value === path) {
        clearEditorSelection()
      }
      if (inlineRenameFilePath.value === path) {
        cancelInlineRenameFile()
      }
      void refreshVersionChanges()
      toast.success(t('agent.editor.deleteFileSuccess'))
    }
    deleteConfirmOpen.value = false
    deleteConfirmChapterId.value = ''
    deleteConfirmFilePath.value = ''
    deleteConfirmLabel.value = ''
  } catch (error) {
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    toast.error(detail || (error instanceof Error ? error.message : t('agent.editor.deleteFailed')))
  } finally {
    deleteConfirmSubmitting.value = false
  }
}

async function handleImportFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  chapterImporting.value = true
  chapterImportMessage.value = null
  try {
    for (const file of files) {
      const content = await file.text()
      const title = file.name.replace(/\.(txt|md|markdown)$/i, '')
      await projectStore.createChapter(props.projectId, { title, content })
    }
    chapterImportMessage.value = t('agent.browser.importFiles', { count: files.length })
  } catch {
    chapterImportMessage.value = t('agent.browser.importFailed')
  } finally {
    chapterImporting.value = false
  }
}

function beginInlineRename(chapterId: string) {
  const chapter = orderedChapters.value.find((c) => c.id === chapterId)
  if (!chapter) return
  inlineRenameChapterId.value = chapterId
  inlineRenameChapterTitle.value = chapter.title || ''
}

function cancelInlineRename() {
  inlineRenameChapterId.value = ''
  inlineRenameChapterTitle.value = ''
}

async function submitInlineRename() {
  const chapterId = inlineRenameChapterId.value
  const title = inlineRenameChapterTitle.value.trim()
  if (!chapterId || inlineRenameSubmitting.value) return
  if (!title) {
    cancelInlineRename()
    return
  }
  inlineRenameSubmitting.value = true
  try {
    await projectStore.updateChapter(props.projectId, chapterId, { title })
  } finally {
    inlineRenameSubmitting.value = false
    cancelInlineRename()
  }
}

function beginInlineRenameFile(path: string) {
  const file = projectFiles.value.find((item) => item.path === path)
  if (!file) return
  inlineRenameFilePath.value = path
  inlineRenameFileName.value = file.name
}

function cancelInlineRenameFile() {
  inlineRenameFilePath.value = ''
  inlineRenameFileName.value = ''
}

async function submitInlineRenameFile() {
  const oldPath = inlineRenameFilePath.value
  const newName = inlineRenameFileName.value.trim()
  if (!oldPath || inlineRenameSubmitting.value) return
  if (!newName) {
    cancelInlineRenameFile()
    return
  }
  const slash = oldPath.lastIndexOf('/')
  const dir = slash >= 0 ? `${oldPath.slice(0, slash + 1)}` : ''
  const newPath = `${dir}${newName}`
  if (newPath === oldPath) {
    cancelInlineRenameFile()
    return
  }
  inlineRenameSubmitting.value = true
  try {
    await renameProjectFile(props.projectId, oldPath, newPath)
    await loadProjectFiles()
    if (editorKind.value === 'file' && activeFilePath.value === oldPath) {
      await selectFile(newPath)
    }
    toast.success(t('agent.editor.renameFileSuccess'))
  } catch (error) {
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    toast.error(detail || (error instanceof Error ? error.message : t('agent.editor.renameFileFailed')))
  } finally {
    inlineRenameSubmitting.value = false
    cancelInlineRenameFile()
  }
}

function handleRenameChapter(chapterId: string) {
  beginInlineRename(chapterId)
}

function handleRenameFile(path: string) {
  beginInlineRenameFile(path)
}

function onEditorDraftUpdate(value: string) {
  if (editorReadOnly.value) return
  editorDraft.value = value
}

let autoSaveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleAutoSave() {
  if (editorKind.value !== 'chapter' || !activeChapterId.value || editorReadOnly.value) return
  if (editorDraft.value === editorBaseline.value) return
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => {
    void saveActiveEditor()
  }, AUTO_SAVE_MS)
}

watch(editorDraft, () => {
  scheduleAutoSave()
})

onBeforeUnmount(() => {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
})

function selectPanel(panelId: BrowserPanelId) {
  if (!layoutStore.isBrowserPanelOpen(panelId)) return
  activePanel.value = panelId
  panelPickerOpen.value = false
}

function openOptionalPanel(panelId: BrowserPanelId) {
  layoutStore.openBrowserPanel(panelId)
  activePanel.value = panelId
  panelPickerOpen.value = false
}

function closeOptionalPanel(panelId: BrowserPanelId) {
  if (activePanel.value === panelId) {
    activePanel.value = 'editor'
  }
  layoutStore.closeBrowserPanel(panelId)
}

function togglePanelPicker() {
  panelPickerOpen.value = !panelPickerOpen.value
}

watch(
  () => [...layoutStore.openOptionalPanels],
  (panels, prev) => {
    const added = panels.find((id) => !prev.includes(id))
    if (added) activePanel.value = added
    if (!layoutStore.isBrowserPanelOpen(activePanel.value)) {
      activePanel.value = 'editor'
    }
  }
)

watch(
  () => props.projectId,
  () => {
    void refreshVersionChanges()
  },
  { immediate: true }
)

// ---- Versions panel ----

const sessionStatusLabel = computed(() => String(agentStore.currentSession?.status || '').toLowerCase())

function ensureEditorLoaded() {
  if (editorLoaded.value) return
  editorLoaded.value = true
  if (!editorKind.value && orderedChapters.value[0]) {
    selectChapter(orderedChapters.value[0].id)
  }
  void loadProjectFiles()
}

watch(activePanel, (next) => {
  if (next === 'editor') {
    ensureEditorLoaded()
  }
  if (next === 'graph' && !graphOpened.value) {
    graphOpened.value = true
    void loadMemoryGraph()
  }
  if (next === 'entities' && !entitiesOpened.value) {
    entitiesOpened.value = true
    void entitiesPanelRef.value?.reload?.()
  }
  if (next === 'versions') {
    void refreshVersionChanges()
  }
})

watch(
  () => [props.projectId, sessionStatusLabel.value] as const,
  ([projectId, status], [, prevStatus]) => {
    if (!projectId) return
    const finished = ['completed', 'partial', 'failed'].includes(status)
    const wasRunning = prevStatus === 'running' || prevStatus === 'pending'
    if (graphOpened.value && finished && wasRunning) {
      void loadMemoryGraph()
    }
    if (entitiesOpened.value && finished && wasRunning) {
      void entitiesPanelRef.value?.reload?.()
    }
  }
)

ensureEditorLoaded()
</script>

<template>
  <section class="muse-workspace-panel muse-workspace-panel-browser">
    <div class="flex min-h-0 flex-1 flex-col">
      <nav
        class="muse-activity-bar muse-activity-bar-top"
        data-testid="agent-activity-bar"
        :aria-label="t('agent.browser.activityBar')"
      >
        <div
          v-for="item in activityBarTabs"
          :key="item.id"
          class="muse-activity-bar-tab-wrap"
        >
          <button
            type="button"
            :data-testid="`agent-activity-${item.id}`"
            :title="item.id === 'versions' && versionChangeCount ? versionChangeLabel : item.label"
            :aria-label="item.id === 'versions' && versionChangeCount ? `${item.label} (${versionChangeLabel})` : item.label"
            :class="cn(
              'muse-activity-bar-tab',
              item.pinned && 'muse-activity-bar-tab-pinned',
              activePanel === item.id && 'muse-activity-bar-tab-active'
            )"
            @click="selectPanel(item.id)"
          >
            <component :is="item.icon" class="h-3.5 w-3.5 shrink-0" />
            <span class="muse-activity-bar-tab-label">{{ item.label }}</span>
            <span
              v-if="item.id === 'versions' && versionChangeCount"
              class="muse-activity-bar-badge"
              data-testid="agent-activity-versions-badge"
              :aria-hidden="true"
            >
              {{ versionChangeCount > 9 ? '9+' : versionChangeCount }}
            </span>
          </button>
          <button
            v-if="!item.pinned"
            type="button"
            class="muse-activity-bar-tab-close"
            :data-testid="`agent-activity-close-${item.id}`"
            :title="t('agent.browser.closePanel')"
            :aria-label="t('agent.browser.closePanelNamed', { name: item.label })"
            @click.stop="closeOptionalPanel(item.id)"
          >
            <X class="h-3 w-3" />
          </button>
        </div>

        <div v-if="availableOptionalPanels.length" class="relative">
          <button
            type="button"
            class="muse-activity-bar-item muse-activity-bar-add"
            data-testid="agent-activity-add"
            :title="t('agent.browser.openPanel')"
            :aria-label="t('agent.browser.openPanel')"
            :aria-expanded="panelPickerOpen"
            @click="togglePanelPicker"
          >
            <Plus class="h-4 w-4" />
          </button>
          <div
            v-if="panelPickerOpen"
            class="muse-activity-bar-picker"
            data-testid="agent-activity-picker"
          >
            <button
              v-for="item in availableOptionalPanels"
              :key="item.id"
              type="button"
              class="muse-activity-bar-picker-item"
              :data-testid="`agent-activity-picker-${item.id}`"
              @click="openOptionalPanel(item.id)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
      </nav>

      <div class="muse-browser-content">
        <!-- Editor panel: kept mounted to preserve selection -->
        <div v-show="activePanel === 'editor'" class="muse-editor-layout">
          <AgentFileExplorer
            :chapters="orderedChapters"
            :files="projectFiles"
            :files-loading="projectFilesLoading"
            :active-kind="editorKind"
            :active-chapter-id="activeChapterId"
            :active-file-path="activeFilePath"
            :search-query="explorerSearchQuery"
            :chapter-importing="chapterImporting"
            :chapter-import-message="chapterImportMessage"
            :can-delete-chapter="Boolean(activeChapter)"
            :inline-rename-chapter-id="inlineRenameChapterId"
            :inline-rename-chapter-title="inlineRenameChapterTitle"
            :inline-rename-file-path="inlineRenameFilePath"
            :inline-rename-file-name="inlineRenameFileName"
            :inline-rename-submitting="inlineRenameSubmitting"
            :chapter-accept="CHAPTER_ACCEPT"
            @update:search-query="explorerSearchQuery = $event"
            @update:inline-rename-chapter-title="inlineRenameChapterTitle = $event"
            @update:inline-rename-file-name="inlineRenameFileName = $event"
            @select-chapter="selectChapter"
            @select-file="selectFile"
            @create-chapter="handleCreateChapter"
            @delete-chapter="handleDeleteActiveChapter"
            @delete-chapter-by-id="handleDeleteChapterById"
            @delete-file="handleDeleteFile"
            @import-files="handleImportFiles"
            @begin-inline-rename="beginInlineRename"
            @submit-inline-rename="submitInlineRename"
            @cancel-inline-rename="cancelInlineRename"
            @begin-inline-rename-file="beginInlineRenameFile"
            @submit-inline-rename-file="submitInlineRenameFile"
            @cancel-inline-rename-file="cancelInlineRenameFile"
            @rename-chapter="handleRenameChapter"
            @rename-file="handleRenameFile"
          />
          <div class="muse-editor-column flex min-h-0 flex-1 flex-col">
            <AgentEditorPane
            :title="editorTitle"
            :breadcrumb="editorBreadcrumb"
            :model-value="editorDraft"
            :placeholder="t('agent.browser.chapterPlaceholder')"
            :read-only="editorReadOnly"
            :dirty="editorDirty"
            :saving="editorSaving"
            :has-selection="hasEditorSelection"
            :empty-message="t('agent.browser.createOrSelectChapter')"
            @update:model-value="onEditorDraftUpdate"
            @save="saveActiveEditor"
          />
          </div>
        </div>

        <!-- Graph panel -->
        <div v-show="activePanel === 'graph'" class="flex min-h-0 flex-1 flex-col muse-workspace-scroll">
          <div class="border-b border-[color:var(--muse-border)] p-3">
            <h3 class="text-sm font-semibold muse-text-heading">{{ t('agent.browser.panels.graph') }}</h3>
            <p class="mt-1 text-[11px] muse-text-faint">
              {{ t('agent.browser.graphStatsWorkspace', { count: workspaceGraphData.nodes.length }) }}
            </p>
            <p class="mt-2 text-[11px] muse-text-faint">{{ t('agent.browser.graphEntitiesHint') }}</p>
          </div>
          <div class="min-h-0 flex-1">
            <GraphPanel v-if="workspaceGraphData.nodes.length" :data="workspaceGraphData" />
            <div v-else class="flex h-full items-center justify-center p-4 text-xs muse-text-faint">
              {{ t('agent.browser.noGraphNodes') }}
            </div>
          </div>
        </div>

        <!-- Memory panel -->
        <div v-show="activePanel === 'memory'" class="flex min-h-0 flex-1 flex-col">
          <AgentMemoryPanel :project-id="projectId" :workspace="workspace" />
        </div>

        <!-- Entities / Facts panel -->
        <div v-show="activePanel === 'entities'" class="flex min-h-0 flex-1 flex-col">
          <AgentEntitiesPanel
            ref="entitiesPanelRef"
            :project-id="projectId"
            :workspace="workspace"
            :ontology="projectStore.currentProject?.ontology_schema || null"
          />
        </div>

        <!-- Versions panel -->
        <div v-show="activePanel === 'versions'" class="min-h-0 flex-1">
          <AgentVersionsPanel :project-id="projectId" />
        </div>

        <!-- Sub-agents panel (Phase B) -->
      </div>
    </div>

    <Modal
      :show="deleteConfirmOpen"
      :title="deleteConfirmKind === 'chapter' ? t('agent.editor.deleteChapterTitle') : t('agent.editor.deleteFileTitle')"
      @close="closeDeleteConfirm"
    >
      <p class="text-sm muse-text-muted">
        {{ deleteConfirmKind === 'chapter'
          ? t('agent.editor.deleteChapterDescription', { name: deleteConfirmLabel })
          : t('agent.editor.deleteFileDescription', { name: deleteConfirmLabel }) }}
      </p>
      <div class="mt-6 flex flex-wrap justify-end gap-2">
        <Button variant="secondary" :disabled="deleteConfirmSubmitting" @click="closeDeleteConfirm">
          {{ t('common.cancel') }}
        </Button>
        <Button
          variant="danger"
          data-testid="agent-explorer-delete-confirm"
          :loading="deleteConfirmSubmitting"
          @click="confirmDelete"
        >
          {{ t('agent.editor.deleteConfirm') }}
        </Button>
      </div>
    </Modal>
  </section>
</template>
