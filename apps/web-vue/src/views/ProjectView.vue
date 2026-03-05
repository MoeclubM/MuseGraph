<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useToast } from '@/composables/useToast'
import AppLayout from '@/components/layout/AppLayout.vue'
import ProjectAIOperationsShell from '@/components/project/ProjectAIOperationsShell.vue'
import ProjectChapterExplorer from '@/components/project/ProjectChapterExplorer.vue'
import ProjectChapterContextMenu from '@/components/project/ProjectChapterContextMenu.vue'
import ProjectEditorPanel from '@/components/project/ProjectEditorPanel.vue'
import ProjectRightAIContent from '@/components/project/ProjectRightAIContent.vue'
import ProjectRightGraphContent from '@/components/project/ProjectRightGraphContent.vue'
import ProjectTaskCenter from '@/components/project/ProjectTaskCenter.vue'
import ProjectWorkspaceHeader from '@/components/project/ProjectWorkspaceHeader.vue'
import { useProjectKnowledgeBase } from '@/composables/useProjectKnowledgeBase'
import {
  runOperation,
  getEmbeddingModels,
  getModels,
  createProjectChapter,
} from '@/api/projects'
import type { ModelInfo } from '@/api/projects'
import { createSimulation, listSimulations } from '@/api/simulation'
import {
  cancelGraphTask,
  getGraphStatus,
  getOasisTaskStatus,
  getVisualization,
  listGraphTasks,
  startAnalyzeOasisTask,
  startBuildGraphTask,
  startGenerateOntologyTask,
  startPrepareOasisTask,
  startReportOasisTask,
  startRunOasisTask,
} from '@/api/graph'
import type {
  ComponentModelConfig,
  Operation,
  GraphData,
  GraphStatus,
  OasisTask,
  ProjectOntology,
  ProjectOasisAnalysis,
  ProjectChapter,
  SimulationRuntime,
} from '@/types'
import { extractTextFromDocument, GRAPH_DOCUMENT_ACCEPT } from '@/utils/document'
import {
  Sparkles,
  ArrowRight,
  Search,
  RefreshCw,
  FileText,
  Network,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const toast = useToast()

const projectId = computed(() => route.params.id as string)
const content = ref('')
const activeChapterId = ref<string>('')
const selectedChapterIds = ref<string[]>([])
const chapterTitleDraft = ref('')
const chapterSearchQuery = ref('')
const inlineRenameChapterId = ref('')
const inlineRenameChapterTitle = ref('')
const inlineRenameSubmitting = ref(false)
const projectTitleEditing = ref(false)
const projectTitleDraft = ref('')
const projectTitleSaving = ref(false)
const saving = ref(false)
type OperationType = 'CREATE' | 'CONTINUE' | 'ANALYZE' | 'REWRITE' | 'SUMMARIZE'
const operationType = ref<OperationType>('CREATE')
const componentModels = ref<ComponentModelConfig>({})
const operationLoading = ref(false)
const operationResult = ref<string | null>(null)
const operationError = ref<string | null>(null)
const continuationApplyMode = ref<'append' | 'replace' | 'new_chapter'>('new_chapter')
const createUserPrompt = ref('')
const createOutline = ref('')
const createOutlineLoading = ref(false)
const createOutlineError = ref<string | null>(null)
const continueUserInstruction = ref('')
const continueOutline = ref('')
const continueOutlineLoading = ref(false)
const continueOutlineError = ref<string | null>(null)
const confirmedSimulationId = ref('')

const {
  projectCharacters,
  selectedCharacterIds,
  charactersLoading,
  charactersError,
  characterFormOpen,
  characterFormSubmitting,
  editingCharacterId,
  characterForm,
  selectedCharacters,
  allCharactersSelected,
  characterSelectionCountLabel,
  loadCharacters,
  beginCreateCharacter,
  beginEditCharacter,
  cancelCharacterForm,
  handleSubmitCharacter,
  handleDeleteCharacter,
  toggleCharacterScope,
  setAllCharactersSelected,
  projectGlossaryTerms,
  selectedGlossaryTermIds,
  glossaryLoading,
  glossaryError,
  glossaryFormOpen,
  glossaryFormSubmitting,
  editingGlossaryTermId,
  glossaryForm,
  selectedGlossaryTerms,
  allGlossaryTermsSelected,
  glossarySelectionCountLabel,
  loadGlossaryTerms,
  beginCreateGlossaryTerm,
  beginEditGlossaryTerm,
  cancelGlossaryForm,
  handleSubmitGlossaryTerm,
  handleDeleteGlossaryTerm,
  toggleGlossaryScope,
  setAllGlossaryTermsSelected,
  projectWorldbookEntries,
  selectedWorldbookEntryIds,
  worldbookLoading,
  worldbookError,
  worldbookFormOpen,
  worldbookFormSubmitting,
  editingWorldbookEntryId,
  worldbookForm,
  selectedWorldbookEntries,
  allWorldbookEntriesSelected,
  worldbookSelectionCountLabel,
  loadWorldbookEntries,
  beginCreateWorldbookEntry,
  beginEditWorldbookEntry,
  cancelWorldbookForm,
  handleSubmitWorldbookEntry,
  handleDeleteWorldbookEntry,
  toggleWorldbookScope,
  setAllWorldbookEntriesSelected,
  resetKnowledgeBaseState,
} = useProjectKnowledgeBase({
  projectId,
  parseError,
  notifySuccess: (message) => toast.success(message),
  notifyError: (message) => toast.error(message),
})

const graphData = ref<GraphData>({ nodes: [], edges: [] })
type GraphFreshnessState = 'no_ontology' | 'empty' | 'syncing' | 'stale' | 'fresh'
const graphStatus = ref<GraphStatus | null>(null)
const graphLoading = ref(false)
const graphError = ref<string | null>(null)
const graphBuildProgress = ref(0)
const graphBuildMessage = ref('')
const graphParsingFile = ref<string | null>(null)
const graphInputCacheText = ref('')
const graphBuildMode = ref<'rebuild' | 'incremental'>('rebuild')
type GraphBuildSummary = {
  status: string
  requestedMode: string
  mode: string
  modeReason: string
  reason: string
  changedCount: number
  addedCount: number
  modifiedCount: number
  removedCount: number
}
const graphBuildSummary = ref<GraphBuildSummary | null>(null)

const ONTOLOGY_PRESET_PROMPT = `请基于当前章节文本构建可用于 RAG 与剧情推理的本体（Ontology），要求：
1. 实体类型覆盖：人物、组织、地点、事件、时间、物品、关系角色；
2. 关系类型需明确方向与语义，例如：BELONGS_TO、LOCATED_IN、PARTICIPATES_IN、CAUSES、PRECEDES；
3. 避免泛化占位类型（如仅 CONCEPT/RELATED_TO），名称使用清晰的英文大写下划线；
4. 输出实体与关系必须可直接用于图谱入库与后续检索增强生成。`

const ontologyLoading = ref(false)
const ontologyError = ref<string | null>(null)
const ontologyData = ref<ProjectOntology | null>(null)
const oasisAnalysisData = ref<ProjectOasisAnalysis | null>(null)
const ontologyProgress = ref(0)
const ontologyMessage = ref('')
const ontologyRequirement = ref(ONTOLOGY_PRESET_PROMPT)

const graphAnalysisPrompt = ref('Generate OASIS analysis and continuation guidance based on this graph.')
const graphAnalysisLoading = ref(false)
const graphAnalysisError = ref<string | null>(null)
const graphAnalysisResult = ref<string | null>(null)
const oasisPackage = ref<Record<string, any> | null>(null)
const oasisRunResult = ref<Record<string, any> | null>(null)
const oasisReport = ref<Record<string, any> | null>(null)
const oasisPrepareLoading = ref(false)
const oasisPrepareError = ref<string | null>(null)
const oasisTask = ref<OasisTask | null>(null)
const oasisTaskError = ref<string | null>(null)
const oasisTaskPolling = ref(false)
const oasisTaskLastId = ref<string>('')
let oasisTaskTimer: ReturnType<typeof setInterval> | null = null

const pipelineTask = ref<OasisTask | null>(null)
const pipelineTaskError = ref<string | null>(null)
const pipelineTaskPolling = ref(false)
let pipelineTaskTimer: ReturnType<typeof setInterval> | null = null
const taskList = ref<OasisTask[]>([])
const taskListLoading = ref(false)
const taskListError = ref<string | null>(null)
const taskListFilter = ref<'all' | 'running' | 'completed' | 'failed' | 'cancelled'>('all')
const taskCenterExpanded = ref(false)
const cancellingTaskIds = ref<string[]>([])
let taskListTimer: ReturnType<typeof setInterval> | null = null
const TASK_LIST_POLL_MS = 6000
const TASK_DETAIL_POLL_MS = 3000

const models = ref<ModelInfo[]>([])
const embeddingModels = ref<ModelInfo[]>([])
const modelsLoading = ref(false)
const chapterImporting = ref(false)
const chapterImportMessage = ref<string | null>(null)
const chapterContextMenu = ref({
  visible: false,
  chapterId: '',
  x: 0,
  y: 0,
})
const simulationLoading = ref(false)
const simulationCreating = ref(false)
const simulationError = ref<string | null>(null)
const projectSimulations = ref<SimulationRuntime[]>([])
type RightPanelTabKey = 'graph' | 'ai' | 'oasis'
const rightPanelTab = ref<RightPanelTabKey>('graph')
const rightPanelTabs: Array<{ key: RightPanelTabKey; label: string; icon: any }> = [
  { key: 'graph', label: 'Graph + RAG', icon: Network },
  { key: 'ai', label: 'AI Create', icon: Sparkles },
  { key: 'oasis', label: 'OASIS Sim', icon: RefreshCw },
]
const isMobileLayout = ref(false)
const leftPanelCollapsed = ref(false)
const rightPanelCollapsed = ref(false)

const selectedChapters = computed(() => {
  const ids = selectedChapterIds.value.length ? selectedChapterIds.value : (activeChapterId.value ? [activeChapterId.value] : [])
  return ids
    .map((id) => findChapterById(id))
    .filter((chapter): chapter is ProjectChapter => !!chapter)
})

const filteredChapters = computed(() => {
  const keyword = chapterSearchQuery.value.trim().toLowerCase()
  const chapters = projectStore.orderedChapters || []
  if (!keyword) return chapters
  return chapters.filter((chapter) => {
    const title = String(chapter.title || '').toLowerCase()
    const chapterIndex = `chapter ${chapter.order_index + 1}`
    return title.includes(keyword) || chapterIndex.includes(keyword)
  })
})

const workflowSourceText = computed(() => {
  const merged = selectedChapters.value
    .map((chapter) => (chapter.content || '').trim())
    .filter(Boolean)
    .join('\n\n')
    .trim()
  return merged || (content.value || '').trim()
})

const workspaceTextLength = computed(() => {
  const chapters = projectStore.orderedChapters || []
  if (!chapters.length) {
    return (content.value || '').trim().length
  }
  const activeId = activeChapterId.value
  return chapters.reduce((sum, chapter) => {
    const source = chapter.id === activeId ? content.value : (chapter.content || '')
    return sum + source.trim().length
  }, 0)
})
const isWorkspaceEmpty = computed(() => workspaceTextLength.value === 0)
const graphCanBuild = computed(() => !!workflowSourceText.value)
const ontologyMeta = computed(() => ontologyData.value?._meta || null)
const ontologyIsConceptOnly = computed(() => {
  const data = ontologyData.value
  if (!data) return false
  const entities = data.entity_types || []
  const edges = data.edge_types || []
  if (entities.length !== 1 || edges.length !== 1) return false
  return entities[0]?.name === 'CONCEPT' && edges[0]?.name === 'RELATED_TO'
})
const hasOntology = computed(() => {
  const data = ontologyData.value
  if (!data) return false
  const entityCount = data.entity_types?.length || 0
  const edgeCount = data.edge_types?.length || 0
  if (entityCount <= 0 || edgeCount <= 0) return false
  if (ontologyIsConceptOnly.value) return false
  return true
})
const hasOasisAnalysis = computed(() => !!oasisAnalysisData.value?.scenario_summary)
const graphReady = computed(() => {
  if (graphStatus.value?.dataset_id) return true
  return !!projectStore.currentProject?.cognee_dataset_id
})
const draftDirty = computed(() => {
  const chapter = findChapterById(activeChapterId.value)
  if (!chapter) return false
  return (content.value || '') !== (chapter.content || '')
})
const latestGraphBuildCompletedAtMs = computed(() => {
  const completed = taskList.value
    .filter((task) => task.task_type === 'graph_build' && task.status === 'completed')
    .map((task) => Date.parse(task.updated_at || '') || 0)
    .filter((value) => value > 0)
  if (!completed.length) return 0
  return Math.max(...completed)
})
const latestChapterMutationAtMs = computed(() => {
  const chapters = projectStore.orderedChapters || []
  const values = chapters
    .map((chapter) => Date.parse(chapter.updated_at || '') || 0)
    .filter((value) => value > 0)
  if (!values.length) return 0
  return Math.max(...values)
})

function normalizeGraphFreshness(value: unknown): GraphFreshnessState | null {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'no_ontology') return 'no_ontology'
  if (normalized === 'empty') return 'empty'
  if (normalized === 'syncing') return 'syncing'
  if (normalized === 'stale') return 'stale'
  if (normalized === 'fresh') return 'fresh'
  return null
}

const graphFreshnessState = computed<GraphFreshnessState>(() => {
  const apiState = normalizeGraphFreshness(graphStatus.value?.graph_freshness)
  if (apiState) return apiState
  if (!hasOntology.value) return 'no_ontology'
  if (graphLoading.value || pipelineTaskPolling.value && pipelineTask.value?.task_type === 'graph_build') return 'syncing'
  if (!graphReady.value) return 'empty'
  if (draftDirty.value) return 'stale'
  const latestBuild = latestGraphBuildCompletedAtMs.value
  const latestChapter = latestChapterMutationAtMs.value
  if (!latestBuild) return 'stale'
  if (latestChapter > latestBuild + 1000) return 'stale'
  return 'fresh'
})
const graphFreshnessLabel = computed(() => {
  const state = graphFreshnessState.value
  if (state === 'no_ontology') return 'Ontology required'
  if (state === 'empty') return 'Graph not built'
  if (state === 'syncing') return 'Graph syncing...'
  if (state === 'stale') return 'Graph stale'
  return 'Graph up to date'
})
const graphFreshnessHint = computed(() => {
  const state = graphFreshnessState.value
  const statusPayload = graphStatus.value
  const reason = String(statusPayload?.graph_reason || '').trim()
  if (state === 'no_ontology') {
    return 'Please complete ontology generation before graph build.'
  }
  if (state === 'empty') {
    return reason === 'dataset_missing'
      ? 'No graph dataset found. Build the graph before RAG-dependent operations.'
      : 'Build graph once to enable RAG and graph-based analysis.'
  }
  if (state === 'syncing') {
    const taskId = String(statusPayload?.graph_syncing_task_id || '').trim()
    return taskId
      ? `Graph build task is running (${taskId.slice(0, 8)}...).`
      : 'Graph build task is running.'
  }
  if (state === 'stale') {
    const added = Number(statusPayload?.graph_added_count || 0)
    const modified = Number(statusPayload?.graph_modified_count || 0)
    const removed = Number(statusPayload?.graph_removed_count || 0)
    if (added > 0 || modified > 0 || removed > 0) {
      return `Changes detected: +${added} / ~${modified} / -${removed}. Run incremental update before RAG operations.`
    }
    if (reason === 'graph_baseline_missing_or_scope_changed' || reason === 'graph_hash_state_missing_or_scope_changed') {
      return 'Graph baseline is missing or scope changed. Run a rebuild once, then use incremental updates.'
    }
    return 'Chapters changed after last build. Run incremental update before RAG-dependent operations.'
  }
  const lastBuildAt = String(statusPayload?.graph_last_build_at || '').trim()
  if (lastBuildAt) {
    return `Last synced at ${formatDate(lastBuildAt)}`
  }
  return ''
})
const confirmedSimulation = computed(() =>
  projectSimulations.value.find((sim) => sim.simulation_id === confirmedSimulationId.value) || null
)
const createPrerequisitesReady = computed(() =>
  isWorkspaceEmpty.value && !!createUserPrompt.value.trim() && !!createOutline.value.trim()
)
const continuePrerequisitesReady = computed(() =>
  graphReady.value && !!continueUserInstruction.value.trim() && !!continueOutline.value.trim()
)
const runningTaskCount = computed(
  () => taskList.value.filter((task) => isRunningTaskStatus(task.status)).length
)
const filteredTaskList = computed(() => {
  if (taskListFilter.value === 'all') return taskList.value
  if (taskListFilter.value === 'running') {
    return taskList.value.filter((task) => isRunningTaskStatus(task.status))
  }
  if (taskListFilter.value === 'completed') {
    return taskList.value.filter((task) => task.status === 'completed')
  }
  if (taskListFilter.value === 'cancelled') {
    return taskList.value.filter((task) => task.status === 'cancelled')
  }
  return taskList.value.filter((task) => task.status === 'failed')
})
const oasisPipeline = computed(() => {
  const analysisDone = hasOasisAnalysis.value
  const packageDone = !!oasisPackage.value
  const runDone = !!oasisRunResult.value
  const reportDone = !!oasisReport.value
  return [
    { key: 'analysis', label: 'Analyze', done: analysisDone },
    { key: 'prepare', label: 'Prepare', done: packageDone },
    { key: 'run', label: 'Run', done: runDone },
    { key: 'report', label: 'Report', done: reportDone },
  ]
})

const operationTypes: Array<{ value: OperationType; label: string; icon: Component; description: string }> = [
  { value: 'CREATE', label: 'Create', icon: Sparkles, description: 'Start from zero with base info' },
  { value: 'CONTINUE', label: 'Continue', icon: ArrowRight, description: 'Continue based on uploaded document' },
  { value: 'ANALYZE', label: 'Analyze', icon: Search, description: 'Analyze uploaded document' },
  { value: 'REWRITE', label: 'Rewrite', icon: RefreshCw, description: 'Rewrite uploaded document' },
  { value: 'SUMMARIZE', label: 'Summarize', icon: FileText, description: 'Summarize uploaded document' },
]

function setOperationType(value: string) {
  const normalized = String(value || '').toUpperCase()
  const allowed: OperationType[] = ['CREATE', 'CONTINUE', 'ANALYZE', 'REWRITE', 'SUMMARIZE']
  if (allowed.includes(normalized as OperationType)) {
    operationType.value = normalized as OperationType
  }
}

const operationModelKey = computed(() => `operation_${operationType.value.toLowerCase()}`)

const operationModel = computed({
  get: () => componentModels.value[operationModelKey.value] || '',
  set: (value: string) => setComponentModel(operationModelKey.value, value),
})

const operationPrimaryLabel = computed(() => {
  if (operationType.value === 'CREATE') return '2. Generate Draft From Outline'
  if (operationType.value === 'CONTINUE') return 'Run Continue'
  return `Run ${operationTypes.find((o) => o.value === operationType.value)?.label || operationType.value}`
})

const ontologyModel = computed({
  get: () => componentModels.value.ontology_generation || '',
  set: (value: string) => setComponentModel('ontology_generation', value),
})

const graphBuildModel = computed({
  get: () => componentModels.value.graph_build || componentModels.value.ontology_generation || '',
  set: (value: string) => setComponentModel('graph_build', value),
})

const graphBuildActionLabel = computed(() =>
  graphBuildMode.value === 'incremental'
    ? 'Update Graph Incrementally'
    : 'Build Knowledge Graph (From Zero)'
)

const graphEmbeddingModel = computed({
  get: () => componentModels.value.graph_embedding || '',
  set: (value: string) => setComponentModel('graph_embedding', value),
})

const graphRerankerModel = computed({
  get: () => componentModels.value.graph_reranker || '',
  set: (value: string) => setComponentModel('graph_reranker', value),
})

const oasisAnalysisModel = computed({
  get: () => componentModels.value.oasis_analysis || '',
  set: (value: string) => setComponentModel('oasis_analysis', value),
})

const oasisSimulationModel = computed({
  get: () => componentModels.value.oasis_simulation_config || '',
  set: (value: string) => setComponentModel('oasis_simulation_config', value),
})

const oasisReportModel = computed({
  get: () => componentModels.value.oasis_report || '',
  set: (value: string) => setComponentModel('oasis_report', value),
})

const contextMenuChapter = computed(() => findChapterById(chapterContextMenu.value.chapterId))
const contextMenuChapterInScope = computed(() => selectedChapterIds.value.includes(chapterContextMenu.value.chapterId))
const chapterContextMenuStyle = computed(() => {
  const width = 188
  const height = 160
  const margin = 8
  const maxX = Math.max(margin, window.innerWidth - width - margin)
  const maxY = Math.max(margin, window.innerHeight - height - margin)
  return {
    left: `${Math.min(Math.max(chapterContextMenu.value.x, margin), maxX)}px`,
    top: `${Math.min(Math.max(chapterContextMenu.value.y, margin), maxY)}px`,
  }
})

function parseError(e: any, fallback: string): string {
  return e?.response?.data?.detail || e?.response?.data?.message || e?.message || fallback
}

function beginProjectTitleEdit() {
  if (!projectStore.currentProject) return
  projectTitleDraft.value = projectStore.currentProject.title || ''
  projectTitleEditing.value = true
}

function cancelProjectTitleEdit() {
  projectTitleEditing.value = false
  projectTitleSaving.value = false
  projectTitleDraft.value = projectStore.currentProject?.title || ''
}

async function submitProjectTitleEdit() {
  const project = projectStore.currentProject
  if (!project) return
  const nextTitle = projectTitleDraft.value.trim()
  if (!nextTitle) {
    toast.error('Project name cannot be empty')
    return
  }
  if (nextTitle === (project.title || '').trim()) {
    projectTitleEditing.value = false
    return
  }
  projectTitleSaving.value = true
  try {
    await projectStore.updateProject(projectId.value, { title: nextTitle })
    projectTitleEditing.value = false
    toast.success('Project title updated')
  } catch (e: any) {
    toast.error(parseError(e, 'Failed to update project title'))
  } finally {
    projectTitleSaving.value = false
  }
}

function applyResponsivePanelPreference(force = false) {
  const mobile = window.innerWidth < 1024
  const layoutChanged = mobile !== isMobileLayout.value
  isMobileLayout.value = mobile
  if (force || layoutChanged) {
    leftPanelCollapsed.value = mobile
    rightPanelCollapsed.value = mobile
  }
}

function handleWindowResize() {
  applyResponsivePanelPreference()
}

function isPageVisible(): boolean {
  if (typeof document === 'undefined') return true
  return document.visibilityState === 'visible'
}

function handleVisibilityChange() {
  if (!isPageVisible()) return
  void loadTaskList(true)
  if (pipelineTaskPolling.value && pipelineTask.value?.task_id) {
    void pollPipelineTask(pipelineTask.value.task_id)
  }
  if (oasisTaskPolling.value && oasisTask.value?.task_id) {
    void pollOasisTask(oasisTask.value.task_id)
  }
}

function toggleLeftPanel() {
  const next = !leftPanelCollapsed.value
  leftPanelCollapsed.value = next
  if (isMobileLayout.value && !next) {
    rightPanelCollapsed.value = true
  }
}

function toggleRightPanel() {
  const next = !rightPanelCollapsed.value
  rightPanelCollapsed.value = next
  if (isMobileLayout.value && !next) {
    leftPanelCollapsed.value = true
  }
}

function sortTasksByCreated(tasks: OasisTask[]): OasisTask[] {
  return [...tasks].sort((a, b) => {
    const at = Date.parse(a.created_at || '') || 0
    const bt = Date.parse(b.created_at || '') || 0
    return bt - at
  })
}

function normalizeIdListCount(value: unknown): number {
  return Array.isArray(value) ? value.filter((item) => !!String(item || '').trim()).length : 0
}

function extractGraphBuildSummary(task: OasisTask | null): GraphBuildSummary | null {
  if (!task || task.task_type !== 'graph_build') return null
  const result = task.result
  if (!result || typeof result !== 'object') return null
  const status = String(result.status || task.status || '').trim()
  const requestedMode = String(result.requested_mode || '').trim()
  const mode = String(result.mode || '').trim()
  const modeReason = String(result.mode_reason || '').trim()
  const reason = String(result.reason || '').trim()
  const changedCount = normalizeIdListCount((result as Record<string, unknown>).changed_chapter_ids)
  const addedCount = normalizeIdListCount((result as Record<string, unknown>).added_chapter_ids)
  const modifiedCount = normalizeIdListCount((result as Record<string, unknown>).modified_chapter_ids)
  const removedCount = normalizeIdListCount((result as Record<string, unknown>).removed_chapter_ids)
  if (!status && !mode && !requestedMode && !reason && !modeReason && changedCount <= 0 && addedCount <= 0 && modifiedCount <= 0 && removedCount <= 0) {
    return null
  }
  return {
    status,
    requestedMode,
    mode,
    modeReason,
    reason,
    changedCount,
    addedCount,
    modifiedCount,
    removedCount,
  }
}

function formatGraphBuildSummary(summary: GraphBuildSummary | null): string {
  if (!summary) return ''
  const modeLabel = summary.mode || summary.requestedMode || 'unknown'
  const changeBits = [
    `changed ${summary.changedCount}`,
    `added ${summary.addedCount}`,
    `modified ${summary.modifiedCount}`,
    `removed ${summary.removedCount}`,
  ]
  return `${modeLabel} · ${changeBits.join(' / ')}`
}

function syncGraphBuildSummaryFromTask(task: OasisTask | null) {
  const summary = extractGraphBuildSummary(task)
  if (summary) {
    graphBuildSummary.value = summary
  }
}

function syncGraphBuildSummaryFromTasks(tasks: OasisTask[]) {
  const latestGraphTask = sortTasksByCreated(tasks).find((item) => item.task_type === 'graph_build')
  if (!latestGraphTask) return
  syncGraphBuildSummaryFromTask(latestGraphTask)
}

function upsertTaskListItem(task: OasisTask) {
  const normalizedTaskId = String(task.task_id || '')
  if (!normalizedTaskId) return
  const next = [...taskList.value]
  const existingIndex = next.findIndex((item) => item.task_id === normalizedTaskId)
  if (existingIndex >= 0) {
    next[existingIndex] = task
  } else {
    next.push(task)
  }
  taskList.value = sortTasksByCreated(next)
  syncGraphBuildSummaryFromTask(task)
}

function replaceTaskList(tasks: OasisTask[]) {
  taskList.value = sortTasksByCreated(tasks)
  syncGraphBuildSummaryFromTasks(taskList.value)
}

async function loadTaskList(silent = false) {
  if (!silent) {
    taskListLoading.value = true
    taskListError.value = null
  }
  try {
    const response = await listGraphTasks(projectId.value, { limit: 100 })
    const tasks = Array.isArray(response.tasks) ? response.tasks : []
    replaceTaskList(tasks)
    await loadGraphStatus(true)
  } catch (e: any) {
    if (!silent) {
      taskListError.value = parseError(e, 'Failed to load task list')
    }
  } finally {
    if (!silent) {
      taskListLoading.value = false
    }
  }
}

function stopTaskListPolling() {
  if (taskListTimer) {
    clearInterval(taskListTimer)
    taskListTimer = null
  }
}

function startTaskListPolling() {
  stopTaskListPolling()
  taskListTimer = setInterval(() => {
    if (!isPageVisible()) return
    void loadTaskList(true)
  }, TASK_LIST_POLL_MS)
}

async function handleRefreshTaskList() {
  await loadTaskList()
}

async function loadGraphStatus(silent = true) {
  try {
    graphStatus.value = await getGraphStatus(projectId.value)
  } catch (e: any) {
    if (!silent && !graphError.value) {
      graphError.value = parseError(e, 'Failed to load graph status')
    }
  }
}

function taskTypeLabel(taskType: string): string {
  const labels: Record<string, string> = {
    ontology_generate: 'Ontology',
    graph_build: 'Graph Build',
    oasis_analyze: 'OASIS Analyze',
    oasis_prepare: 'OASIS Prepare',
    oasis_run: 'OASIS Run',
    oasis_report: 'OASIS Report',
  }
  return labels[taskType] || taskType
}

function isRunningTaskStatus(status: string): boolean {
  const normalized = String(status || '').toLowerCase()
  return normalized === 'pending' || normalized === 'processing'
}

function syncCancelledTask(task: OasisTask) {
  if (pipelineTask.value?.task_id === task.task_id) {
    pipelineTask.value = task
    stopPipelineTaskPolling()
    ontologyLoading.value = false
    graphLoading.value = false
    if (task.task_type === 'ontology_generate') {
      ontologyMessage.value = task.message || 'Ontology task cancelled'
    } else if (task.task_type === 'graph_build') {
      graphBuildMessage.value = task.message || 'Graph build task cancelled'
    }
  }
  if (oasisTask.value?.task_id === task.task_id) {
    oasisTask.value = task
    stopOasisTaskPolling()
    graphAnalysisLoading.value = false
    oasisPrepareLoading.value = false
  }
}

async function handleCancelTask(task: OasisTask) {
  if (!task?.task_id || !isRunningTaskStatus(task.status)) return
  if (cancellingTaskIds.value.includes(task.task_id)) return
  cancellingTaskIds.value = [...cancellingTaskIds.value, task.task_id]
  try {
    const response = await cancelGraphTask(projectId.value, task.task_id)
    const latest = response.task
    upsertTaskListItem(latest)
    syncPipelineProgress(latest)
    if (latest.status === 'cancelled') {
      syncCancelledTask(latest)
      toast.success(`${taskTypeLabel(latest.task_type)} task cancelled`)
    } else {
      toast.success(`${taskTypeLabel(latest.task_type)} task is already ${latest.status}`)
    }
  } catch (e: any) {
    toast.error(parseError(e, 'Failed to cancel task'))
  } finally {
    cancellingTaskIds.value = cancellingTaskIds.value.filter((id) => id !== task.task_id)
  }
}

function stopPipelineTaskPolling() {
  if (pipelineTaskTimer) {
    clearInterval(pipelineTaskTimer)
    pipelineTaskTimer = null
  }
  pipelineTaskPolling.value = false
}

function syncPipelineProgress(task: OasisTask) {
  if (task.task_type === 'ontology_generate') {
    ontologyLoading.value = isRunningTaskStatus(task.status)
    ontologyProgress.value = Math.max(0, Math.min(100, Number(task.progress || 0)))
    ontologyMessage.value = task.message || 'Generating ontology...'
  } else if (task.task_type === 'graph_build') {
    graphLoading.value = isRunningTaskStatus(task.status)
    graphBuildProgress.value = Math.max(0, Math.min(100, Number(task.progress || 0)))
    graphBuildMessage.value = task.message || 'Building knowledge graph...'
  }
}

async function applyPipelineTaskResult(task: OasisTask) {
  const result = task.result || {}
  if (task.task_type === 'ontology_generate' && result.ontology && typeof result.ontology === 'object') {
    ontologyData.value = result.ontology as ProjectOntology
    ontologyProgress.value = 100
    ontologyMessage.value = task.message || 'Ontology generated'
    ontologyError.value = null
    await loadProject()
  } else if (task.task_type === 'graph_build') {
    syncGraphBuildSummaryFromTask(task)
    const summaryText = formatGraphBuildSummary(graphBuildSummary.value)
    graphBuildProgress.value = 100
    graphBuildMessage.value = task.message || 'Knowledge graph built'
    if (summaryText) {
      graphBuildMessage.value = `${graphBuildMessage.value} · ${summaryText}`
    }
    graphError.value = null
    await loadGraphData()
    await loadProject()
  }
}

async function pollPipelineTask(taskId: string) {
  try {
    const data = await getOasisTaskStatus(projectId.value, taskId)
    pipelineTask.value = data.task
    upsertTaskListItem(data.task)
    syncPipelineProgress(data.task)
    if (data.task.task_type === 'graph_build') {
      await loadGraphStatus(true)
    }
    if (data.task.task_type === 'graph_build' && isRunningTaskStatus(data.task.status)) {
      await loadGraphData({ preserveOnError: true })
    }
    if (data.task.status === 'completed') {
      stopPipelineTaskPolling()
      await applyPipelineTaskResult(data.task)
    } else if (data.task.status === 'cancelled') {
      syncCancelledTask(data.task)
    } else if (data.task.status === 'failed') {
      stopPipelineTaskPolling()
      if (data.task.task_type === 'ontology_generate') {
        ontologyLoading.value = false
        ontologyError.value = data.task.error || data.task.message || 'Ontology task failed'
      } else if (data.task.task_type === 'graph_build') {
        graphLoading.value = false
        graphError.value = data.task.error || data.task.message || 'Graph build task failed'
      }
      pipelineTaskError.value = data.task.error || data.task.message || 'Task failed'
    }
  } catch (e: any) {
    const wasOntologyLoading = ontologyLoading.value
    const wasGraphLoading = graphLoading.value
    stopPipelineTaskPolling()
    ontologyLoading.value = false
    graphLoading.value = false
    const message = parseError(e, 'Failed to fetch pipeline task status')
    pipelineTaskError.value = message
    const taskType = pipelineTask.value?.task_type || ''
    if (taskType === 'ontology_generate' || wasOntologyLoading) {
      ontologyError.value = message
    }
    if (taskType === 'graph_build' || wasGraphLoading) {
      graphError.value = message
    }
  }
}

function startPipelineTaskPolling(taskId: string) {
  stopPipelineTaskPolling()
  pipelineTaskPolling.value = true
  void pollPipelineTask(taskId)
  pipelineTaskTimer = setInterval(() => {
    if (!isPageVisible()) return
    void pollPipelineTask(taskId)
  }, TASK_DETAIL_POLL_MS)
}

function stopOasisTaskPolling() {
  if (oasisTaskTimer) {
    clearInterval(oasisTaskTimer)
    oasisTaskTimer = null
  }
  oasisTaskPolling.value = false
}

async function applyOasisTaskResult(task: OasisTask) {
  const result = task.result || {}
  if (result.analysis && typeof result.analysis === 'object') {
    oasisAnalysisData.value = result.analysis as ProjectOasisAnalysis
    graphAnalysisResult.value = formatOasisAnalysis(result.analysis as ProjectOasisAnalysis)
    graphAnalysisError.value = null
  }
  if (result.package && typeof result.package === 'object') {
    oasisPackage.value = result.package
  }
  if (result.run_result && typeof result.run_result === 'object') {
    oasisRunResult.value = result.run_result
  }
  if (result.report && typeof result.report === 'object') {
    oasisReport.value = result.report
  }
  await loadProject()
}

async function pollOasisTask(taskId: string) {
  try {
    const data = await getOasisTaskStatus(projectId.value, taskId)
    oasisTask.value = data.task
    oasisTaskLastId.value = data.task.task_id
    if (data.task.task_type === 'oasis_analyze') {
      graphAnalysisLoading.value = isRunningTaskStatus(data.task.status)
    }
    upsertTaskListItem(data.task)
    if (data.task.status === 'completed') {
      stopOasisTaskPolling()
      if (data.task.task_type === 'oasis_analyze') {
        graphAnalysisLoading.value = false
      }
      await applyOasisTaskResult(data.task)
    } else if (data.task.status === 'cancelled') {
      syncCancelledTask(data.task)
    } else if (data.task.status === 'failed') {
      stopOasisTaskPolling()
      if (data.task.task_type === 'oasis_analyze') {
        graphAnalysisLoading.value = false
        graphAnalysisError.value = data.task.error || data.task.message || 'OASIS analysis task failed'
      }
      oasisTaskError.value = data.task.error || data.task.message || 'OASIS task failed'
    }
  } catch (e: any) {
    stopOasisTaskPolling()
    graphAnalysisLoading.value = false
    oasisTaskError.value = parseError(e, 'Failed to fetch OASIS task status')
  }
}

function startOasisTaskPolling(taskId: string) {
  stopOasisTaskPolling()
  oasisTaskLastId.value = taskId
  oasisTaskPolling.value = true
  void pollOasisTask(taskId)
  oasisTaskTimer = setInterval(() => {
    if (!isPageVisible()) return
    void pollOasisTask(taskId)
  }, TASK_DETAIL_POLL_MS)
}

async function handleRefreshOasisTaskStatus() {
  const taskId = oasisTask.value?.task_id || oasisTaskLastId.value
  if (!taskId) {
    oasisTaskError.value = 'No OASIS task id available to refresh'
    return
  }
  oasisTaskError.value = null
  await pollOasisTask(taskId)
}

function normalizeComponentModels(raw: ComponentModelConfig | null | undefined): ComponentModelConfig {
  if (!raw || typeof raw !== 'object') return {}
  const next: ComponentModelConfig = {}
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value === 'string' && value.trim()) {
      next[key] = value.trim()
    }
  }
  return next
}

async function persistComponentModels() {
  try {
    await projectStore.updateProject(projectId.value, { component_models: componentModels.value })
  } catch {
    // API interceptor handles toast
  }
}

function setComponentModel(key: string, value: string) {
  const normalized = (value || '').trim()
  const next: ComponentModelConfig = { ...componentModels.value }
  if (normalized) {
    next[key] = normalized
  } else {
    delete next[key]
  }
  componentModels.value = next
  void persistComponentModels()
}

async function resolveGraphInputText(forPhase: 'ontology' | 'build'): Promise<string> {
  const text = workflowSourceText.value
  if (!text) {
    throw new Error(
      forPhase === 'ontology'
        ? 'No chapter text available for ontology generation'
        : 'No chapter text available for graph build'
    )
  }
  graphInputCacheText.value = text
  return text
}

async function resolveWorkflowRequestText(forPhase: 'ontology' | 'build'): Promise<string> {
  const scope = chapterScopePayload()
  if (scope.chapter_ids && scope.chapter_ids.length > 0) {
    // For chapter-scoped runs, let backend merge persisted chapter content.
    graphInputCacheText.value = workflowSourceText.value
    return ''
  }
  return resolveGraphInputText(forPhase)
}

function findChapterById(chapterId: string): ProjectChapter | null {
  return (projectStore.orderedChapters || []).find((chapter) => chapter.id === chapterId) || null
}

function syncActiveChapterContentFromState() {
  const chapter = findChapterById(activeChapterId.value)
  if (chapter) {
    content.value = chapter.content || ''
    chapterTitleDraft.value = chapter.title || ''
    return
  }
  content.value = ''
  chapterTitleDraft.value = ''
}

function hasUnsavedDraftChanges(): boolean {
  return draftDirty.value
}

function buildContinuationChapterTitle(nextOrder: number): string {
  const heading = continueOutline.value
    .split('\n')
    .map((line) => line.trim())
    .find((line) => !!line)
    || continueUserInstruction.value
      .split('\n')
      .map((line) => line.trim())
      .find((line) => !!line)
    || ''
  const cleaned = heading
    .replace(/^[-*#\d.\)\s]+/, '')
    .replace(/^chapter\s*\d+\s*[:：-]?\s*/i, '')
    .trim()
  const title = cleaned.slice(0, 80)
  return title || `Chapter ${nextOrder + 1}`
}

async function applyCreateOutput(output: string): Promise<string[]> {
  const chapter = findChapterById(activeChapterId.value)
  if (!chapter) {
    content.value = output
    return []
  }
  const title = chapterTitleDraft.value.trim() || chapter.title || `Chapter ${chapter.order_index + 1}`
  await projectStore.updateChapter(projectId.value, chapter.id, {
    title,
    content: output,
  })
  if (!selectedChapterIds.value.includes(chapter.id)) {
    selectedChapterIds.value = [...selectedChapterIds.value, chapter.id]
  }
  syncActiveChapterContentFromState()
  return [chapter.id]
}

async function applyContinuationOutput(output: string): Promise<string[]> {
  if (continuationApplyMode.value === 'new_chapter') {
    const nextOrder = projectStore.orderedChapters.length
    const created = await projectStore.createChapter(projectId.value, {
      title: buildContinuationChapterTitle(nextOrder),
      content: output,
      order_index: nextOrder,
    })
    const newest = created[created.length - 1]
    if (newest) {
      activeChapterId.value = newest.id
      selectedChapterIds.value = [newest.id]
      syncActiveChapterContentFromState()
      return [newest.id]
    }
    return []
  }

  const chapter = findChapterById(activeChapterId.value)
  if (!chapter) {
    content.value = continuationApplyMode.value === 'replace'
      ? output
      : (content.value ? `${content.value}\n\n${output}` : output)
    return []
  }

  const currentContent = chapter.content || ''
  const mergedContent = continuationApplyMode.value === 'replace'
    ? output
    : (currentContent ? `${currentContent}\n\n${output}` : output)
  const title = chapterTitleDraft.value.trim() || chapter.title || `Chapter ${chapter.order_index + 1}`
  await projectStore.updateChapter(projectId.value, chapter.id, {
    title,
    content: mergedContent,
  })
  if (!selectedChapterIds.value.includes(chapter.id)) {
    selectedChapterIds.value = [...selectedChapterIds.value, chapter.id]
  }
  syncActiveChapterContentFromState()
  return [chapter.id]
}

function chapterScopePayload(): { chapter_ids?: string[] } {
  return selectedChapterIds.value.length ? { chapter_ids: selectedChapterIds.value } : {}
}

async function ensureChapterStateInitialized() {
  if (!projectStore.currentProject) return
  const chapters = projectStore.orderedChapters
  if (!chapters.length) {
    await projectStore.fetchChapters(projectId.value)
  }

  const ordered = projectStore.orderedChapters
  if (!ordered.length) {
    activeChapterId.value = ''
    selectedChapterIds.value = []
    content.value = ''
    return
  }

  if (!activeChapterId.value || !findChapterById(activeChapterId.value)) {
    activeChapterId.value = ordered[0].id
  }

  if (!selectedChapterIds.value.length) {
    // Default graph/ontology pipeline scope is the whole project chapters.
    selectedChapterIds.value = ordered.map((chapter) => chapter.id)
  } else {
    selectedChapterIds.value = selectedChapterIds.value.filter((id) => !!findChapterById(id))
    if (!selectedChapterIds.value.length) {
      selectedChapterIds.value = ordered.map((chapter) => chapter.id)
    }
  }

  syncActiveChapterContentFromState()
}

async function handleSelectChapter(chapterId: string) {
  if (chapterId === activeChapterId.value) return
  if (hasUnsavedDraftChanges()) {
    const shouldSwitch = window.confirm('You have unsaved changes in the current chapter. Switch chapter and discard local draft changes?')
    if (!shouldSwitch) return
  }
  activeChapterId.value = chapterId
  if (!selectedChapterIds.value.includes(chapterId)) {
    selectedChapterIds.value = [chapterId, ...selectedChapterIds.value]
  }
  syncActiveChapterContentFromState()
}

function openChapterContextMenu(event: MouseEvent, chapterId: string) {
  chapterContextMenu.value = {
    visible: true,
    chapterId,
    x: event.clientX,
    y: event.clientY,
  }
}

function closeChapterContextMenu() {
  chapterContextMenu.value.visible = false
}

function handleGlobalPointerDown(event: PointerEvent) {
  if (!chapterContextMenu.value.visible) return
  const target = event.target as HTMLElement | null
  if (target?.closest?.('[data-chapter-context-menu="true"]')) return
  closeChapterContextMenu()
}

function handleGlobalKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && inlineRenameChapterId.value) {
    cancelInlineRenameChapter()
    return
  }
  if (event.key === 'Escape') {
    closeChapterContextMenu()
  }
}

function toggleChapterForWorkflow(chapterId: string) {
  if (selectedChapterIds.value.includes(chapterId)) {
    if (selectedChapterIds.value.length === 1) return
    selectedChapterIds.value = selectedChapterIds.value.filter((id) => id !== chapterId)
    if (!selectedChapterIds.value.includes(activeChapterId.value)) {
      activeChapterId.value = selectedChapterIds.value[0] || activeChapterId.value
      syncActiveChapterContentFromState()
    }
    return
  }
  selectedChapterIds.value = [...selectedChapterIds.value, chapterId]
}

async function beginInlineRenameChapter(chapterId: string) {
  const chapter = findChapterById(chapterId)
  if (!chapter) return
  inlineRenameChapterId.value = chapterId
  inlineRenameChapterTitle.value = chapter.title || `Chapter ${chapter.order_index + 1}`
}

function cancelInlineRenameChapter() {
  inlineRenameChapterId.value = ''
  inlineRenameChapterTitle.value = ''
}

async function submitInlineRenameChapter() {
  if (inlineRenameSubmitting.value) return
  const chapterId = inlineRenameChapterId.value
  if (!chapterId) return
  const chapter = findChapterById(chapterId)
  if (!chapter) {
    cancelInlineRenameChapter()
    return
  }
  const fallbackTitle = chapter.title || `Chapter ${chapter.order_index + 1}`
  const title = inlineRenameChapterTitle.value.trim() || fallbackTitle
  if (title === fallbackTitle) {
    cancelInlineRenameChapter()
    return
  }
  inlineRenameSubmitting.value = true
  try {
    await projectStore.updateChapter(projectId.value, chapter.id, { title })
    if (activeChapterId.value === chapterId) {
      chapterTitleDraft.value = title
    }
    cancelInlineRenameChapter()
  } finally {
    inlineRenameSubmitting.value = false
  }
}

async function deleteChapterById(chapterId: string) {
  const chapter = findChapterById(chapterId)
  if (!chapter) return
  if (projectStore.orderedChapters.length <= 1) {
    toast.error('At least one chapter must remain')
    return
  }
  const chapterName = chapter.title || `Chapter ${chapter.order_index + 1}`
  if (!window.confirm(`Delete "${chapterName}"?`)) return

  await projectStore.deleteChapter(projectId.value, chapterId)
  if (inlineRenameChapterId.value === chapterId) {
    cancelInlineRenameChapter()
  }
  const remaining = projectStore.orderedChapters
  if (!remaining.length) {
    activeChapterId.value = ''
    selectedChapterIds.value = []
    content.value = ''
    return
  }

  if (!findChapterById(activeChapterId.value)) {
    activeChapterId.value = remaining[0].id
  }
  selectedChapterIds.value = selectedChapterIds.value.filter((id) => id !== chapterId)
  if (!selectedChapterIds.value.length) {
    selectedChapterIds.value = [activeChapterId.value]
  }
  syncActiveChapterContentFromState()
}

async function handleContextMenuOpen() {
  const chapter = contextMenuChapter.value
  if (!chapter) return
  closeChapterContextMenu()
  await handleSelectChapter(chapter.id)
}

async function handleContextMenuRename() {
  const chapter = contextMenuChapter.value
  if (!chapter) return
  closeChapterContextMenu()
  await beginInlineRenameChapter(chapter.id)
}

function handleContextMenuToggleScope() {
  const chapter = contextMenuChapter.value
  if (!chapter) return
  closeChapterContextMenu()
  toggleChapterForWorkflow(chapter.id)
}

async function handleContextMenuDelete() {
  const chapter = contextMenuChapter.value
  if (!chapter) return
  closeChapterContextMenu()
  await deleteChapterById(chapter.id)
}

async function handleCreateChapter() {
  const nextOrder = projectStore.orderedChapters.length
  await projectStore.createChapter(projectId.value, {
    title: `Chapter ${nextOrder + 1}`,
    content: '',
    order_index: nextOrder,
  })
  const newest = projectStore.orderedChapters[projectStore.orderedChapters.length - 1]
  if (newest) {
    activeChapterId.value = newest.id
    if (!selectedChapterIds.value.includes(newest.id)) {
      selectedChapterIds.value = [...selectedChapterIds.value, newest.id]
    }
    syncActiveChapterContentFromState()
  }
}

function normalizeChapterTitleFromFile(fileName: string): string {
  const trimmed = (fileName || '').trim()
  if (!trimmed) return 'Untitled chapter'
  const dot = trimmed.lastIndexOf('.')
  const base = dot > 0 ? trimmed.slice(0, dot) : trimmed
  return base.trim() || 'Untitled chapter'
}

async function handleChapterFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length || chapterImporting.value) return

  chapterImporting.value = true
  chapterImportMessage.value = null
  let orderIndex = projectStore.orderedChapters.length
  let successCount = 0
  const failedFiles: string[] = []

  try {
    for (let i = 0; i < files.length; i += 1) {
      const file = files[i]
      chapterImportMessage.value = `Importing (${i + 1}/${files.length}): ${file.name}`
      try {
        const text = await extractTextFromDocument(file)
        await createProjectChapter(projectId.value, {
          title: normalizeChapterTitleFromFile(file.name),
          content: (text || '').trim(),
          order_index: orderIndex,
        })
        orderIndex += 1
        successCount += 1
      } catch {
        failedFiles.push(file.name)
      }
    }

    await projectStore.fetchProject(projectId.value)
    await projectStore.fetchChapters(projectId.value)
    await ensureChapterStateInitialized()

    if (successCount > 0) {
      toast.success(`Imported ${successCount} file(s) as chapters`)
    }
    if (failedFiles.length > 0) {
      toast.error(`Failed to import: ${failedFiles.join(', ')}`)
    }
  } finally {
    chapterImporting.value = false
    chapterImportMessage.value = null
  }
}

async function handleDeleteActiveChapter() {
  if (!activeChapterId.value) return
  await deleteChapterById(activeChapterId.value)
}

function formatOasisAnalysis(analysis: ProjectOasisAnalysis | null): string {
  if (!analysis) return 'No OASIS analysis output returned.'
  const lines: string[] = []
  if (analysis.scenario_summary) {
    lines.push(`Scenario: ${analysis.scenario_summary}`)
  }
  if (analysis.key_drivers?.length) {
    lines.push('Key Drivers:')
    lines.push(...analysis.key_drivers.slice(0, 8).map((item) => `- ${item}`))
  }
  if (analysis.continuation_guidance?.next_steps?.length) {
    lines.push('Next Steps:')
    lines.push(...analysis.continuation_guidance.next_steps.slice(0, 8).map((item) => `- ${item}`))
  }
  if (analysis.continuation_guidance?.avoid?.length) {
    lines.push('Avoid:')
    lines.push(...analysis.continuation_guidance.avoid.slice(0, 8).map((item) => `- ${item}`))
  }
  if (analysis.simulation_config?.time_config) {
    const t = analysis.simulation_config.time_config
    lines.push('Simulation Time Config:')
    lines.push(`- Total Hours: ${t.total_hours}`)
    lines.push(`- Minutes Per Round: ${t.minutes_per_round}`)
    lines.push(`- Peak Hours: ${(t.peak_hours || []).join(', ') || 'N/A'}`)
  }
  if (analysis.simulation_config?.events?.length) {
    lines.push('Planned Events:')
    lines.push(
      ...analysis.simulation_config.events
        .slice(0, 6)
        .map((event) => `- H+${event.trigger_hour}: ${event.title}${event.description ? ` (${event.description})` : ''}`)
    )
  }
  if (analysis.simulation_config?.agent_activity?.length) {
    lines.push(`Agent Activity Config: ${analysis.simulation_config.agent_activity.length} agents`)
  }
  return lines.join('\n')
}

async function loadProjectSimulations() {
  simulationLoading.value = true
  simulationError.value = null
  try {
    projectSimulations.value = await listSimulations(projectId.value)
  } catch (e: any) {
    simulationError.value = parseError(e, 'Failed to load workflow simulations')
    projectSimulations.value = []
  } finally {
    simulationLoading.value = false
  }
}

async function handleCreateWorkflowSimulation() {
  const project = projectStore.currentProject
  if (!project || !project.cognee_dataset_id) {
    simulationError.value = 'Please build knowledge graph before creating simulation'
    return
  }
  simulationCreating.value = true
  simulationError.value = null
  try {
    await persistActiveChapterDraftIfNeeded()
    const result = await createSimulation({
      project_id: project.id,
      graph_id: project.cognee_dataset_id,
      enable_twitter: true,
      enable_reddit: true,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
    })
    await loadProjectSimulations()
    confirmedSimulationId.value = ''
    toast.success('Simulation created')
    await router.push(`/simulation/${result.simulation_id}`)
  } catch (e: any) {
    simulationError.value = parseError(e, 'Failed to create simulation')
  } finally {
    simulationCreating.value = false
  }
}

async function loadProject() {
  await projectStore.fetchProject(projectId.value)
  await loadGraphStatus(true)
  if (projectStore.currentProject) {
    ontologyData.value = projectStore.currentProject.ontology_schema || null
    const savedOasis = projectStore.currentProject.oasis_analysis || null
    oasisAnalysisData.value = savedOasis
    graphAnalysisResult.value = savedOasis ? formatOasisAnalysis(savedOasis) : null
    oasisPackage.value =
      savedOasis && typeof savedOasis.latest_package === 'object' && savedOasis.latest_package
        ? savedOasis.latest_package
        : null
    oasisRunResult.value =
      savedOasis && typeof savedOasis.latest_run === 'object' && savedOasis.latest_run
        ? savedOasis.latest_run
        : null
    oasisReport.value =
      savedOasis && typeof savedOasis.latest_report === 'object' && savedOasis.latest_report
        ? savedOasis.latest_report
        : null
    ontologyRequirement.value = projectStore.currentProject.simulation_requirement || ONTOLOGY_PRESET_PROMPT
    componentModels.value = normalizeComponentModels(projectStore.currentProject.component_models)
    projectTitleDraft.value = projectStore.currentProject.title || ''
  }
  await ensureChapterStateInitialized()
  await projectStore.fetchOperations(projectId.value)
  await Promise.all([loadCharacters(), loadGlossaryTerms(), loadWorldbookEntries()])
  await loadProjectSimulations()
  if (projectStore.currentProject?.cognee_dataset_id) {
    await loadGraphData()
  } else {
    graphData.value = { nodes: [], edges: [] }
  }
  await resumeProjectTasks()
}

async function resumeProjectTasks() {
  try {
    const response = await listGraphTasks(projectId.value, { limit: 60 })
    const tasks = Array.isArray(response.tasks) ? response.tasks : []
    replaceTaskList(tasks)
    taskListError.value = null
    if (!tasks.length) return

    const running = (task: OasisTask) => isRunningTaskStatus(task.status)
    const pipelineRunning = tasks.find((task) =>
      running(task) && (task.task_type === 'ontology_generate' || task.task_type === 'graph_build')
    )
    if (pipelineRunning) {
      syncPipelineProgress(pipelineRunning)
      taskCenterExpanded.value = true
      startPipelineTaskPolling(pipelineRunning.task_id)
    }

    const oasisRunning = tasks.find((task) =>
      running(task)
      && (
        task.task_type === 'oasis_analyze'
        || task.task_type === 'oasis_prepare'
        || task.task_type === 'oasis_run'
        || task.task_type === 'oasis_report'
      )
    )
    if (oasisRunning) {
      taskCenterExpanded.value = true
      startOasisTaskPolling(oasisRunning.task_id)
    } else {
      const latestOasis = tasks.find((task) =>
        task.task_type === 'oasis_analyze'
        || task.task_type === 'oasis_prepare'
        || task.task_type === 'oasis_run'
        || task.task_type === 'oasis_report'
      )
      if (latestOasis) {
        oasisTaskLastId.value = latestOasis.task_id
      }
    }
  } catch (e: any) {
    taskListError.value = parseError(e, 'Failed to load task list')
  }
}

async function handleSave() {
  saving.value = true
  try {
    await persistActiveChapterDraftIfNeeded({ triggerGraphRefresh: true })
    await ensureChapterStateInitialized()
    toast.success('Project saved')
  } catch {
    // API interceptor handles the error toast
  } finally {
    saving.value = false
  }
}

async function persistActiveChapterDraftIfNeeded(
  options: { triggerGraphRefresh?: boolean } = {}
): Promise<string[]> {
  const activeChapter = findChapterById(activeChapterId.value)
  if (!activeChapter) return []
  const nextTitle = chapterTitleDraft.value.trim() || activeChapter.title || 'Untitled chapter'
  const nextContent = content.value
  const currentTitle = activeChapter.title || ''
  const currentContent = activeChapter.content || ''
  if (nextTitle === currentTitle && nextContent === currentContent) {
    return []
  }
  await projectStore.updateChapter(projectId.value, activeChapter.id, {
    title: nextTitle,
    content: nextContent,
  })
  chapterTitleDraft.value = nextTitle
  const changedChapterIds = [activeChapter.id]
  if (options.triggerGraphRefresh) {
    void triggerIncrementalGraphRefresh(changedChapterIds)
  }
  return changedChapterIds
}

function normalizeChapterIds(chapterIds: string[]): string[] {
  const seen = new Set<string>()
  const normalized: string[] = []
  for (const raw of chapterIds) {
    const id = String(raw || '').trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    normalized.push(id)
  }
  return normalized
}

async function triggerIncrementalGraphRefresh(chapterIds: string[] = []) {
  if (!hasOntology.value) return
  if (graphLoading.value) return
  const normalized = normalizeChapterIds(chapterIds)
  graphBuildSummary.value = null
  try {
    const response = await startBuildGraphTask(projectId.value, {
      chapter_ids: normalized.length ? normalized : undefined,
      build_mode: 'incremental',
    })
    pipelineTask.value = response.task
    upsertTaskListItem(response.task)
    syncPipelineProgress(response.task)
    taskCenterExpanded.value = true
    startPipelineTaskPolling(response.task.task_id)
    toast.success('RAG graph refresh started (incremental)')
  } catch (e: any) {
    toast.error(parseError(e, 'Failed to refresh graph incrementally'))
  }
}

async function handleOperation() {
  const op = operationType.value
  if (op !== 'CREATE' && !graphReady.value) {
    operationError.value = 'Knowledge graph is required for this operation. Please build graph first.'
    return
  }
  operationLoading.value = true
  operationResult.value = null
  operationError.value = null
  try {
    if (op === 'CREATE') {
      if (!isWorkspaceEmpty.value) {
        operationError.value = 'CREATE is only available when workspace text length is 0.'
        return
      }
      if (!createUserPrompt.value.trim()) {
        operationError.value = 'Please provide a creation prompt before CREATE.'
        return
      }
      if (!createOutline.value.trim()) {
        operationError.value = 'Please generate and confirm outline before CREATE.'
        return
      }
    }
    await persistActiveChapterDraftIfNeeded()
    if (op === 'CONTINUE') {
      if (!continueUserInstruction.value.trim()) {
        operationError.value = 'Please provide continuation instruction before CONTINUE.'
        return
      }
      if (!continueOutline.value.trim()) {
        operationError.value = 'Please generate continuation outline before CONTINUE.'
        return
      }
    }
    const input =
      op === 'CREATE'
        ? [
            'Generate a full draft strictly based on the outline below.',
            'Stay faithful to the user prompt and keep narrative consistency.',
            '',
            '[User Prompt]',
            createUserPrompt.value.trim(),
            '',
            '[Outline]',
            createOutline.value.trim(),
          ].join('\n')
        : op === 'CONTINUE'
          ? [
              'Continue writing according to the continuation outline and user instruction.',
              'Use graph retrieval context (RAG) to preserve entities, roles, and relationships.',
              '',
              '[User Instruction]',
              continueUserInstruction.value.trim(),
              '',
              '[Continuation Outline]',
              continueOutline.value.trim(),
            ].join('\n')
        : undefined
    const result: Operation = await runOperation(projectId.value, {
      type: op,
      input,
      model: operationModel.value || undefined,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
      character_ids: selectedCharacterIds.value.length ? selectedCharacterIds.value : undefined,
      glossary_term_ids: selectedGlossaryTermIds.value.length ? selectedGlossaryTermIds.value : undefined,
      worldbook_entry_ids: selectedWorldbookEntryIds.value.length ? selectedWorldbookEntryIds.value : undefined,
    })
    operationResult.value = result.output
    let changedChapterIds: string[] = []
    if (result.output && op === 'CONTINUE') {
      changedChapterIds = await applyContinuationOutput(result.output)
    } else if (result.output && op === 'CREATE') {
      changedChapterIds = await applyCreateOutput(result.output)
    }
    toast.success('Operation completed')
    await ensureChapterStateInitialized()
    await projectStore.fetchOperations(projectId.value)
    if (changedChapterIds.length) {
      void triggerIncrementalGraphRefresh(changedChapterIds)
    }
  } catch (e: any) {
    operationError.value = parseError(e, 'Operation failed')
  } finally {
    operationLoading.value = false
  }
}

async function handleGenerateCreateOutline() {
  if (!isWorkspaceEmpty.value) {
    createOutlineError.value = 'CREATE outline is only available when workspace text length is 0.'
    return
  }
  if (!createUserPrompt.value.trim()) {
    createOutlineError.value = 'Please provide a creation prompt first.'
    return
  }
  createOutlineLoading.value = true
  createOutlineError.value = null
  operationError.value = null
  try {
    await persistActiveChapterDraftIfNeeded()
    const input = [
      'Generate a detailed writing outline first.',
      'Output sections: Theme, Plot Arc, Chapter Beats, Character Goals, Risks, Cliffhangers.',
      'Do not use graph retrieval context in this stage; rely on user prompt only.',
      '',
      '[User Prompt]',
      createUserPrompt.value.trim(),
    ].join('\n')
    const result = await runOperation(projectId.value, {
      type: 'CREATE',
      input,
      model: operationModel.value || undefined,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
      character_ids: selectedCharacterIds.value.length ? selectedCharacterIds.value : undefined,
      glossary_term_ids: selectedGlossaryTermIds.value.length ? selectedGlossaryTermIds.value : undefined,
      worldbook_entry_ids: selectedWorldbookEntryIds.value.length ? selectedWorldbookEntryIds.value : undefined,
      use_rag: false,
    })
    createOutline.value = result.output?.trim() || ''
    if (!createOutline.value) {
      createOutlineError.value = 'No outline returned. Please retry.'
      return
    }
    operationResult.value = createOutline.value
    toast.success('Outline generated')
    await projectStore.fetchOperations(projectId.value)
  } catch (e: any) {
    createOutlineError.value = parseError(e, 'Failed to generate outline')
  } finally {
    createOutlineLoading.value = false
  }
}

async function handleGenerateContinueOutline() {
  if (!graphReady.value) {
    continueOutlineError.value = 'Knowledge graph is required before generating continuation outline.'
    return
  }
  if (!continueUserInstruction.value.trim()) {
    continueOutlineError.value = 'Please provide continuation instruction first.'
    return
  }
  continueOutlineLoading.value = true
  continueOutlineError.value = null
  operationError.value = null
  try {
    await persistActiveChapterDraftIfNeeded()
    const result = await runOperation(projectId.value, {
      type: 'ANALYZE',
      input: [
        'Generate a continuation outline before writing the next chapter.',
        'Use RAG context to summarize prior content and character states first, then output follow-up outline.',
        'Output sections: Prior Story Summary, Character State Board, Continuation Goal, Story Beats, Risk Checks, Writing Instructions.',
        '',
        '[User Instruction]',
        continueUserInstruction.value.trim(),
        '',
        '[Selected Chapter Scope]',
        selectedChapters.value.map((chapter) => chapter.title || chapter.id).join(', ') || 'Current chapter only',
      ].join('\n'),
      model: operationModel.value || undefined,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
      character_ids: selectedCharacterIds.value.length ? selectedCharacterIds.value : undefined,
      glossary_term_ids: selectedGlossaryTermIds.value.length ? selectedGlossaryTermIds.value : undefined,
      worldbook_entry_ids: selectedWorldbookEntryIds.value.length ? selectedWorldbookEntryIds.value : undefined,
    })
    continueOutline.value = result.output?.trim() || ''
    if (!continueOutline.value) {
      continueOutlineError.value = 'No continuation outline returned. Please retry.'
      return
    }
    operationResult.value = continueOutline.value
    toast.success('Continuation outline generated')
    await projectStore.fetchOperations(projectId.value)
  } catch (e: any) {
    continueOutlineError.value = parseError(e, 'Failed to generate continuation outline')
  } finally {
    continueOutlineLoading.value = false
  }
}

function canConfirmSimulation(sim: SimulationRuntime): boolean {
  return ['ready', 'completed', 'stopped'].includes((sim.status || '').toLowerCase())
}

function confirmSimulationForContinue(simulationId: string) {
  confirmedSimulationId.value = simulationId
  operationError.value = null
  toast.success('Simulation confirmed for continuation')
}

async function handleGenerateOntology() {
  if (ontologyLoading.value || !graphCanBuild.value) return
  ontologyLoading.value = true
  ontologyError.value = null
  pipelineTaskError.value = null
  ontologyProgress.value = 5
  ontologyMessage.value = 'Preparing ontology generation...'
  graphParsingFile.value = null
  let started = false
  try {
    await persistActiveChapterDraftIfNeeded()
    const sourceText = await resolveWorkflowRequestText('ontology')
    const response = await startGenerateOntologyTask(
      projectId.value,
      {
        text: sourceText || undefined,
        requirement: ontologyRequirement.value || undefined,
        model: ontologyModel.value || undefined,
        chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
      }
    )
    started = true
    pipelineTask.value = response.task
    upsertTaskListItem(response.task)
    syncPipelineProgress(response.task)
    taskCenterExpanded.value = true
    startPipelineTaskPolling(response.task.task_id)
    toast.success('Ontology task started')
  } catch (e: any) {
    ontologyError.value = parseError(e, 'Failed to generate ontology')
  } finally {
    graphParsingFile.value = null
    if (!started) {
      ontologyLoading.value = false
    }
  }
}

async function handleBuildGraph() {
  if (graphLoading.value || !graphCanBuild.value) return
  if (!hasOntology.value) {
    graphError.value = 'Please generate ontology before building the graph'
    return
  }
  graphBuildSummary.value = null
  graphLoading.value = true
  graphError.value = null
  pipelineTaskError.value = null
  graphBuildProgress.value = 5
  graphBuildMessage.value = 'Preparing graph build...'
  graphParsingFile.value = null
  let started = false
  try {
    await persistActiveChapterDraftIfNeeded()
    const sourceText = await resolveWorkflowRequestText('build')
    const response = await startBuildGraphTask(projectId.value, {
      text: sourceText || undefined,
      ontology: ontologyData.value,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
      build_mode: graphBuildMode.value,
    })
    started = true
    pipelineTask.value = response.task
    upsertTaskListItem(response.task)
    syncPipelineProgress(response.task)
    taskCenterExpanded.value = true
    startPipelineTaskPolling(response.task.task_id)
    toast.success(
      graphBuildMode.value === 'incremental'
        ? 'Incremental graph update task started'
        : 'Graph rebuild task started'
    )
  } catch (e: any) {
    graphError.value = parseError(e, 'Failed to build graph')
  } finally {
    graphParsingFile.value = null
    if (!started) {
      graphLoading.value = false
    }
  }
}

async function handleGraphAnalysis() {
  if (graphAnalysisLoading.value || oasisTaskPolling.value || !graphReady.value) return
  graphAnalysisLoading.value = true
  graphAnalysisError.value = null
  graphAnalysisResult.value = null
  continueOutline.value = ''
  continueOutlineError.value = null
  oasisPackage.value = null
  oasisRunResult.value = null
  oasisReport.value = null
  oasisTaskError.value = null
  oasisPrepareError.value = null
  try {
    const sourceText = graphInputCacheText.value.trim()
      ? graphInputCacheText.value
      : content.value.trim()
    const result = await startAnalyzeOasisTask(projectId.value, {
      text: sourceText || undefined,
      prompt: graphAnalysisPrompt.value.trim() || undefined,
      requirement: ontologyRequirement.value.trim() || undefined,
      analysis_model: oasisAnalysisModel.value || undefined,
      simulation_model: oasisSimulationModel.value || undefined,
      chapter_ids: selectedChapterIds.value,
    })
    oasisTask.value = result.task
    upsertTaskListItem(result.task)
    taskCenterExpanded.value = true
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS analysis task started')
  } catch (e: any) {
    graphAnalysisError.value = parseError(e, 'Graph analysis failed')
    graphAnalysisLoading.value = false
  }
}

async function handlePrepareOasisPackage() {
  if (oasisPrepareLoading.value || !graphReady.value) return
  oasisPrepareLoading.value = true
  oasisPrepareError.value = null
  oasisTaskError.value = null
  try {
    const sourceText = graphInputCacheText.value.trim()
      ? graphInputCacheText.value
      : content.value.trim()
    const result = await startPrepareOasisTask(projectId.value, {
      text: sourceText || undefined,
      prompt: graphAnalysisPrompt.value.trim() || undefined,
      requirement: ontologyRequirement.value.trim() || undefined,
      analysis_model: oasisAnalysisModel.value || undefined,
      simulation_model: oasisSimulationModel.value || undefined,
      chapter_ids: selectedChapterIds.value,
    })
    oasisTask.value = result.task
    upsertTaskListItem(result.task)
    taskCenterExpanded.value = true
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS package task started')
  } catch (e: any) {
    oasisPrepareError.value = parseError(e, 'Failed to prepare OASIS package')
  } finally {
    oasisPrepareLoading.value = false
  }
}

async function handleRunOasisSimulation() {
  if (!graphReady.value || !hasOasisAnalysis.value) return
  oasisTaskError.value = null
  try {
    const result = await startRunOasisTask(projectId.value, {
      package: oasisPackage.value || undefined,
      chapter_ids: selectedChapterIds.value,
    })
    oasisTask.value = result.task
    upsertTaskListItem(result.task)
    taskCenterExpanded.value = true
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS run task started')
  } catch (e: any) {
    oasisTaskError.value = parseError(e, 'Failed to start OASIS run task')
  }
}

async function handleGenerateOasisReport() {
  if (!graphReady.value || !hasOasisAnalysis.value) return
  oasisTaskError.value = null
  try {
    const result = await startReportOasisTask(projectId.value, {
      report_model: oasisReportModel.value || undefined,
      chapter_ids: selectedChapterIds.value,
    })
    oasisTask.value = result.task
    upsertTaskListItem(result.task)
    taskCenterExpanded.value = true
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS report task started')
  } catch (e: any) {
    oasisTaskError.value = parseError(e, 'Failed to start OASIS report task')
  }
}

async function loadGraphData(options: { preserveOnError?: boolean } = {}) {
  try {
    graphData.value = await getVisualization(projectId.value)
    graphError.value = null
  } catch (e: any) {
    if (!options.preserveOnError) {
      graphData.value = { nodes: [], edges: [] }
      graphError.value = parseError(e, 'Failed to load graph visualization')
    }
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusColor(status: string) {
  const colors: Record<string, string> = {
    COMPLETED: 'text-emerald-400',
    FAILED: 'text-red-400',
    PROCESSING: 'text-yellow-400',
    PENDING: 'text-stone-500 dark:text-zinc-400',
  }
  return colors[status] || 'text-stone-500 dark:text-zinc-400'
}

function graphFreshnessClass(state: string): string {
  if (state === 'fresh') {
    return 'border-emerald-300/80 bg-emerald-100/70 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300'
  }
  if (state === 'syncing') {
    return 'border-amber-300/80 bg-amber-100/70 text-amber-900 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300'
  }
  if (state === 'stale') {
    return 'border-rose-300/80 bg-rose-100/70 text-rose-900 dark:border-rose-700/50 dark:bg-rose-900/20 dark:text-rose-300'
  }
  return 'border-stone-300/80 bg-stone-100/70 text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/45 dark:text-zinc-300'
}

function oasisTaskStatusColor(status: string) {
  const colors: Record<string, string> = {
    completed: 'text-emerald-700 dark:text-emerald-300',
    failed: 'text-red-700 dark:text-red-300',
    cancelled: 'text-stone-600 dark:text-zinc-400',
    processing: 'text-amber-700 dark:text-amber-300',
    pending: 'text-stone-700 dark:text-zinc-300',
  }
  return colors[status] || 'text-stone-700 dark:text-zinc-300'
}

function oasisStageClass(done: boolean) {
  return done
    ? 'border-emerald-300/70 bg-emerald-100/70 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300'
    : 'border-stone-300 dark:border-zinc-700 bg-stone-100/80 dark:bg-zinc-800/60 text-stone-500 dark:text-zinc-400'
}

async function loadModels() {
  modelsLoading.value = true
  try {
    const [chatModels, embedModels] = await Promise.all([
      getModels(),
      getEmbeddingModels(),
    ])
    models.value = chatModels
    embeddingModels.value = embedModels
  } catch {
    models.value = []
    embeddingModels.value = []
  } finally {
    modelsLoading.value = false
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', handleGlobalPointerDown)
  document.addEventListener('keydown', handleGlobalKeyDown)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  window.addEventListener('resize', handleWindowResize)
  applyResponsivePanelPreference(true)
  startTaskListPolling()
  loadProject()
  loadModels()
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', handleGlobalPointerDown)
  document.removeEventListener('keydown', handleGlobalKeyDown)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('resize', handleWindowResize)
  stopTaskListPolling()
  stopPipelineTaskPolling()
  stopOasisTaskPolling()
})

watch([workflowSourceText, selectedChapterIds], () => {
  graphInputCacheText.value = ''
}, { deep: true })

watch(operationType, (type) => {
  operationError.value = null
  operationResult.value = null
  if (type === 'CONTINUE' && !['append', 'replace', 'new_chapter'].includes(continuationApplyMode.value)) {
    continuationApplyMode.value = 'new_chapter'
  }
  if (type !== 'CREATE') {
    createOutlineError.value = null
  }
  if (type !== 'CONTINUE') {
    continueOutlineError.value = null
  }
})

watch(createUserPrompt, () => {
  createOutline.value = ''
  createOutlineError.value = null
})

watch(continueUserInstruction, () => {
  continueOutline.value = ''
  continueOutlineError.value = null
})

watch(
  () => route.params.id,
  () => {
    if (route.params.id) {
      closeChapterContextMenu()
      projectTitleEditing.value = false
      projectTitleSaving.value = false
      chapterSearchQuery.value = ''
      inlineRenameChapterId.value = ''
      inlineRenameChapterTitle.value = ''
      taskCenterExpanded.value = false
      cancellingTaskIds.value = []
      stopPipelineTaskPolling()
      stopOasisTaskPolling()
      taskList.value = []
      taskListLoading.value = false
      taskListError.value = null
      pipelineTask.value = null
      pipelineTaskError.value = null
      oasisTaskLastId.value = ''
      graphData.value = { nodes: [], edges: [] }
      graphStatus.value = null
      graphLoading.value = false
      graphError.value = null
      graphBuildMessage.value = ''
      graphBuildProgress.value = 0
      ontologyLoading.value = false
      ontologyError.value = null
      ontologyMessage.value = ''
      ontologyProgress.value = 0
      ontologyData.value = null
      oasisAnalysisData.value = null
      graphAnalysisLoading.value = false
      graphAnalysisResult.value = null
      graphAnalysisError.value = null
      oasisPackage.value = null
      oasisRunResult.value = null
      oasisReport.value = null
      oasisPrepareError.value = null
      oasisTask.value = null
      oasisTaskError.value = null
      createUserPrompt.value = ''
      createOutline.value = ''
      createOutlineError.value = null
      continueUserInstruction.value = ''
      continueOutline.value = ''
      continueOutlineError.value = null
      resetKnowledgeBaseState()
      confirmedSimulationId.value = ''
      loadProject()
    }
  }
)

watch(activeChapterId, () => {
  syncActiveChapterContentFromState()
})

watch(
  () => projectSimulations.value.map((sim) => sim.simulation_id),
  (ids) => {
    if (confirmedSimulationId.value && !ids.includes(confirmedSimulationId.value)) {
      confirmedSimulationId.value = ''
    }
  }
)

watch(selectedChapterIds, () => {
  closeChapterContextMenu()
  continueOutline.value = ''
  continueOutlineError.value = null
  confirmedSimulationId.value = ''
})
</script>

<template>
  <AppLayout :padded="false">
    <div v-if="projectStore.projectLoading" class="flex items-center justify-center h-full">
      <div class="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent" />
    </div>

    <div v-else-if="!projectStore.currentProject" class="flex items-center justify-center h-full">
      <p class="text-stone-500 dark:text-zinc-500">Project not found</p>
    </div>

    <div v-else class="h-full flex flex-col bg-[#f7f3e8] text-stone-800 dark:bg-zinc-900 dark:text-zinc-100">
      <ProjectWorkspaceHeader
        :project-title-editing="projectTitleEditing"
        :project-title-draft="projectTitleDraft"
        :project-title-saving="projectTitleSaving"
        :project-title="projectStore.currentProject.title"
        :left-panel-collapsed="leftPanelCollapsed"
        :right-panel-collapsed="rightPanelCollapsed"
        :saving="saving"
        @update:project-title-draft="projectTitleDraft = $event"
        @begin-edit-title="beginProjectTitleEdit"
        @submit-title="submitProjectTitleEdit"
        @cancel-title="cancelProjectTitleEdit"
        @toggle-left-panel="toggleLeftPanel"
        @toggle-right-panel="toggleRightPanel"
        @save="handleSave"
      />

      <div class="flex flex-1 overflow-hidden">
        <!-- Left: File Explorer -->
        <ProjectChapterExplorer
          :left-panel-collapsed="leftPanelCollapsed"
          :chapter-accept="GRAPH_DOCUMENT_ACCEPT"
          :chapter-saving="projectStore.chapterSaving"
          :chapter-importing="chapterImporting"
          :chapter-import-message="chapterImportMessage"
          :selected-chapter-ids="selectedChapterIds"
          :active-chapter-id="activeChapterId"
          :filtered-chapters="filteredChapters"
          :chapter-search-query="chapterSearchQuery"
          :inline-rename-chapter-id="inlineRenameChapterId"
          :inline-rename-chapter-title="inlineRenameChapterTitle"
          :inline-rename-submitting="inlineRenameSubmitting"
          :can-delete-chapter="projectStore.chapterSaving === false && projectStore.orderedChapters.length > 1"
          @update:chapter-search-query="chapterSearchQuery = $event"
          @update:inline-rename-chapter-title="inlineRenameChapterTitle = $event"
          @import-files="handleChapterFileSelect"
          @create-chapter="handleCreateChapter"
          @delete-active-chapter="handleDeleteActiveChapter"
          @open-context-menu="openChapterContextMenu"
          @toggle-chapter-scope="toggleChapterForWorkflow"
          @select-chapter="handleSelectChapter"
          @begin-inline-rename="beginInlineRenameChapter"
          @submit-inline-rename="submitInlineRenameChapter"
          @cancel-inline-rename="cancelInlineRenameChapter"
        />

        <!-- Center: Editor -->
        <ProjectEditorPanel
          :visible="!(isMobileLayout && !rightPanelCollapsed)"
          :right-panel-collapsed="rightPanelCollapsed"
          :chapter-title="findChapterById(activeChapterId)?.title || ''"
          :content="content"
          @update:content="content = $event"
        />

        <!-- Right: AI Operations Panel -->
        <ProjectAIOperationsShell
          :right-panel-collapsed="rightPanelCollapsed"
          :is-mobile-layout="isMobileLayout"
          :right-panel-tab="rightPanelTab"
          :right-panel-tabs="rightPanelTabs"
          :graph-ready="graphReady"
          :operation-type="operationType"
          @update:right-panel-tab="rightPanelTab = $event"
        >
          <template #ai-content>
            <ProjectRightAIContent
              :right-panel-tab="rightPanelTab"
              :selected-characters-count="selectedCharacters.length"
              :character-selection-count-label="characterSelectionCountLabel"
              :characters-loading="charactersLoading"
              :project-characters="projectCharacters"
              :all-characters-selected="allCharactersSelected"
              :characters-error="charactersError"
              :selected-character-ids="selectedCharacterIds"
              :character-form-open="characterFormOpen"
              :editing-character-id="editingCharacterId"
              :character-form="characterForm"
              :character-form-submitting="characterFormSubmitting"
              :load-characters="loadCharacters"
              :begin-create-character="beginCreateCharacter"
              :set-all-characters-selected="setAllCharactersSelected"
              :toggle-character-scope="toggleCharacterScope"
              :begin-edit-character="beginEditCharacter"
              :handle-delete-character="handleDeleteCharacter"
              :cancel-character-form="cancelCharacterForm"
              :handle-submit-character="handleSubmitCharacter"
              :selected-glossary-terms-count="selectedGlossaryTerms.length"
              :glossary-selection-count-label="glossarySelectionCountLabel"
              :glossary-loading="glossaryLoading"
              :project-glossary-terms="projectGlossaryTerms"
              :all-glossary-terms-selected="allGlossaryTermsSelected"
              :glossary-error="glossaryError"
              :selected-glossary-term-ids="selectedGlossaryTermIds"
              :glossary-form-open="glossaryFormOpen"
              :editing-glossary-term-id="editingGlossaryTermId"
              :glossary-form="glossaryForm"
              :glossary-form-submitting="glossaryFormSubmitting"
              :load-glossary-terms="loadGlossaryTerms"
              :begin-create-glossary-term="beginCreateGlossaryTerm"
              :set-all-glossary-terms-selected="setAllGlossaryTermsSelected"
              :toggle-glossary-scope="toggleGlossaryScope"
              :begin-edit-glossary-term="beginEditGlossaryTerm"
              :handle-delete-glossary-term="handleDeleteGlossaryTerm"
              :cancel-glossary-form="cancelGlossaryForm"
              :handle-submit-glossary-term="handleSubmitGlossaryTerm"
              :selected-worldbook-entries-count="selectedWorldbookEntries.length"
              :worldbook-selection-count-label="worldbookSelectionCountLabel"
              :worldbook-loading="worldbookLoading"
              :project-worldbook-entries="projectWorldbookEntries"
              :all-worldbook-entries-selected="allWorldbookEntriesSelected"
              :worldbook-error="worldbookError"
              :selected-worldbook-entry-ids="selectedWorldbookEntryIds"
              :worldbook-form-open="worldbookFormOpen"
              :editing-worldbook-entry-id="editingWorldbookEntryId"
              :worldbook-form="worldbookForm"
              :worldbook-form-submitting="worldbookFormSubmitting"
              :load-worldbook-entries="loadWorldbookEntries"
              :begin-create-worldbook-entry="beginCreateWorldbookEntry"
              :set-all-worldbook-entries-selected="setAllWorldbookEntriesSelected"
              :toggle-worldbook-scope="toggleWorldbookScope"
              :begin-edit-worldbook-entry="beginEditWorldbookEntry"
              :handle-delete-worldbook-entry="handleDeleteWorldbookEntry"
              :cancel-worldbook-form="cancelWorldbookForm"
              :handle-submit-worldbook-entry="handleSubmitWorldbookEntry"
              :operation-types="operationTypes"
              :operation-type="operationType"
              :is-workspace-empty="isWorkspaceEmpty"
              :models-loading="modelsLoading"
              :models="models"
              :operation-model="operationModel"
              :continuation-apply-mode="continuationApplyMode"
              :create-user-prompt="createUserPrompt"
              :create-outline="createOutline"
              :create-outline-loading="createOutlineLoading"
              :create-outline-error="createOutlineError"
              :continue-user-instruction="continueUserInstruction"
              :continue-outline="continueOutline"
              :continue-outline-loading="continueOutlineLoading"
              :continue-outline-error="continueOutlineError"
              :graph-ready="graphReady"
              :create-prerequisites-ready="createPrerequisitesReady"
              :continue-prerequisites-ready="continuePrerequisitesReady"
              :operation-loading="operationLoading"
              :operation-primary-label="operationPrimaryLabel"
              :operation-error="operationError"
              :operation-result="operationResult"
              :operations="projectStore.operations"
              :status-color="statusColor"
              :format-date="formatDate"
              :simulation-loading="simulationLoading"
              :simulation-creating="simulationCreating"
              :simulation-error="simulationError"
              :project-simulations="projectSimulations"
              :confirmed-simulation-id="confirmedSimulationId"
              :can-confirm-simulation="canConfirmSimulation"
              @update:operation-type="setOperationType"
              @update:operation-model="operationModel = $event"
              @update:continuation-apply-mode="continuationApplyMode = $event"
              @update:create-user-prompt="createUserPrompt = $event"
              @update:create-outline="createOutline = $event"
              @update:continue-user-instruction="continueUserInstruction = $event"
              @update:continue-outline="continueOutline = $event"
              @generate-create-outline="handleGenerateCreateOutline"
              @generate-continue-outline="handleGenerateContinueOutline"
              @run-operation="handleOperation"
              @refresh-simulations="loadProjectSimulations"
              @create-simulation="handleCreateWorkflowSimulation"
              @confirm-simulation="confirmSimulationForContinue"
              @open-simulation="(simulationId) => router.push(`/simulation/${simulationId}`)"
            />
          </template>

          <template #graph-content>
            <ProjectRightGraphContent
              :right-panel-tab="rightPanelTab"
              :workflow-source-text-length="workflowSourceText.length"
              :ontology-requirement="ontologyRequirement"
              :models-loading="modelsLoading"
              :models="models"
              :ontology-model="ontologyModel"
              :ontology-loading="ontologyLoading"
              :graph-can-build="graphCanBuild"
              :ontology-message="ontologyMessage"
              :ontology-progress="ontologyProgress"
              :graph-parsing-file="graphParsingFile"
              :ontology-error="ontologyError"
              :ontology-data="ontologyData"
              :has-ontology="hasOntology"
              :ontology-meta="ontologyMeta"
              :graph-build-model="graphBuildModel"
              :embedding-models="embeddingModels"
              :graph-embedding-model="graphEmbeddingModel"
              :graph-reranker-model="graphRerankerModel"
              :graph-build-mode="graphBuildMode"
              :graph-freshness-state="graphFreshnessState"
              :graph-freshness-label="graphFreshnessLabel"
              :graph-freshness-hint="graphFreshnessHint"
              :graph-loading="graphLoading"
              :graph-build-action-label="graphBuildActionLabel"
              :graph-build-message="graphBuildMessage"
              :graph-build-progress="graphBuildProgress"
              :graph-build-summary="graphBuildSummary"
              :graph-error="graphError"
              :format-graph-build-summary="formatGraphBuildSummary"
              :graph-freshness-class="graphFreshnessClass"
              :pipeline="oasisPipeline"
              :graph-ready="graphReady"
              :has-oasis-analysis="hasOasisAnalysis"
              :oasis-task-polling="oasisTaskPolling"
              :oasis-prepare-loading="oasisPrepareLoading"
              :oasis-task="oasisTask"
              :oasis-task-last-id="oasisTaskLastId"
              :graph-analysis-loading="graphAnalysisLoading"
              :graph-analysis-error="graphAnalysisError"
              :oasis-prepare-error="oasisPrepareError"
              :oasis-task-error="oasisTaskError"
              :graph-analysis-result="graphAnalysisResult"
              :oasis-package="oasisPackage"
              :oasis-run-result="oasisRunResult"
              :oasis-report="oasisReport"
              :graph-analysis-prompt="graphAnalysisPrompt"
              :oasis-analysis-model="oasisAnalysisModel"
              :oasis-simulation-model="oasisSimulationModel"
              :oasis-report-model="oasisReportModel"
              :oasis-stage-class="oasisStageClass"
              :oasis-task-status-color="oasisTaskStatusColor"
              :graph-data="graphData"
              :project-id="projectId"
              @update:ontology-requirement="ontologyRequirement = $event"
              @update:ontology-model="ontologyModel = $event"
              @update:graph-build-model="graphBuildModel = $event"
              @update:graph-embedding-model="graphEmbeddingModel = $event"
              @update:graph-reranker-model="graphRerankerModel = $event"
              @update:graph-build-mode="graphBuildMode = $event"
              @generate-ontology="handleGenerateOntology"
              @build-graph="handleBuildGraph"
              @update:graph-analysis-prompt="graphAnalysisPrompt = $event"
              @update:oasis-analysis-model="oasisAnalysisModel = $event"
              @update:oasis-simulation-model="oasisSimulationModel = $event"
              @update:oasis-report-model="oasisReportModel = $event"
              @analyze="handleGraphAnalysis"
              @prepare="handlePrepareOasisPackage"
              @run="handleRunOasisSimulation"
              @report="handleGenerateOasisReport"
              @refresh-status="handleRefreshOasisTaskStatus"
              @open-full-graph="router.push(`/projects/${projectId}/graph`)"
            />
          </template>
        </ProjectAIOperationsShell>
    </div>
    </div>

    <ProjectTaskCenter
      :tasks="taskList"
      :loading="taskListLoading"
      :error="taskListError"
      :expanded="taskCenterExpanded"
      :filter="taskListFilter"
      :cancelling-task-ids="cancellingTaskIds"
      :format-date="formatDate"
      @update:expanded="taskCenterExpanded = $event"
      @update:filter="taskListFilter = $event"
      @refresh="handleRefreshTaskList"
      @cancel="handleCancelTask"
    />

    <ProjectChapterContextMenu
      :visible="chapterContextMenu.visible && !!contextMenuChapter"
      :style="chapterContextMenuStyle"
      :in-scope="contextMenuChapterInScope"
      @open="handleContextMenuOpen"
      @rename="handleContextMenuRename"
      @toggle-scope="handleContextMenuToggleScope"
      @delete="handleContextMenuDelete"
    />
  </AppLayout>
</template>




