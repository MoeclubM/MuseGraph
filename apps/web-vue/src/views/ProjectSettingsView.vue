<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Brain, Download, GitBranch, Globe2, Loader2, Settings2, Sparkles, Trash2 } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import DropdownSelect from '@/components/ui/DropdownSelect.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Modal from '@/components/ui/Modal.vue'
import Input from '@/components/ui/Input.vue'
import { useProjectStore } from '@/stores/project'
import { useToast } from '@/composables/useToast'
import {
  getEmbeddingModels,
  getModels,
  getRerankerModels,
  updateProjectVisibility,
  type ModelInfo,
} from '@/api/projects'
import type { ProjectVisibility } from '@/types'
import {
  deleteProjectMemory,
  getMemoryStatus,
  startMemoryBuildTask,
  getMemoryTask,
  type MemoryStatus,
} from '@/api/memory'
import { downloadBlob, downloadProjectBundle } from '@/api/export'
import type { ComponentModelConfig } from '@/types'

const MEMORY_AUTO_SYNC_KEY = 'memory_auto_sync'
const MEMORY_AUTO_SYNC_DISABLED = 'disabled'

type ModelField = {
  key: string
  labelKey: string
  hintKey: string
  kind: 'chat' | 'embedding' | 'reranker'
}

const MODEL_FIELDS: ModelField[] = [
  { key: 'operation_agent_task', labelKey: 'projectSettings.models.agentTask', hintKey: 'projectSettings.models.agentTaskHint', kind: 'chat' },
  { key: 'operation_agent_suggest', labelKey: 'projectSettings.models.agentSuggest', hintKey: 'projectSettings.models.agentSuggestHint', kind: 'chat' },
  { key: 'ontology_generation', labelKey: 'projectSettings.models.ontology', hintKey: 'projectSettings.models.ontologyHint', kind: 'chat' },
  { key: 'memory_build', labelKey: 'projectSettings.models.memoryBuild', hintKey: 'projectSettings.models.memoryBuildHint', kind: 'chat' },
  { key: 'memory_embedding', labelKey: 'projectSettings.models.memoryEmbedding', hintKey: 'projectSettings.models.memoryEmbeddingHint', kind: 'embedding' },
  { key: 'memory_reranker', labelKey: 'projectSettings.models.memoryReranker', hintKey: 'projectSettings.models.memoryRerankerHint', kind: 'reranker' },
  // Phase C: per-role model overrides for the long-form pipeline.
  // Sub-agent profiles fall back to operation_* keys when these are unset.
  { key: 'role_planner', labelKey: 'projectSettings.models.rolePlanner', hintKey: 'projectSettings.models.rolePlannerHint', kind: 'chat' },
  { key: 'role_composer', labelKey: 'projectSettings.models.roleComposer', hintKey: 'projectSettings.models.roleComposerHint', kind: 'chat' },
  { key: 'role_writer', labelKey: 'projectSettings.models.roleWriter', hintKey: 'projectSettings.models.roleWriterHint', kind: 'chat' },
  { key: 'role_auditor', labelKey: 'projectSettings.models.roleAuditor', hintKey: 'projectSettings.models.roleAuditorHint', kind: 'chat' },
  { key: 'role_reviser', labelKey: 'projectSettings.models.roleReviser', hintKey: 'projectSettings.models.roleReviserHint', kind: 'chat' },
]

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const projectStore = useProjectStore()
const toast = useToast()

const projectId = computed(() => String(route.params.id || ''))
const loading = ref(true)
const savingModels = ref(false)
const memoryLoading = ref(false)
const memoryBuilding = ref(false)
const memoryStatus = ref<MemoryStatus | null>(null)
const componentModels = ref<ComponentModelConfig>({})
const chatModels = ref<ModelInfo[]>([])
const embeddingModels = ref<ModelInfo[]>([])
const rerankerModels = ref<ModelInfo[]>([])
const exportingBundle = ref(false)
const savingVisibility = ref(false)
const deleteModalOpen = ref(false)
const deleteConfirmName = ref('')
const deletingProject = ref(false)

const projectTitle = computed(() => projectStore.currentProject?.title || t('projectSettings.loadingProject'))
const canManageVisibility = computed(() => {
  const permissions = projectStore.currentProject?.current_user_permissions || []
  return permissions.includes('manage')
})
const canDeleteProject = computed(() => {
  const permissions = projectStore.currentProject?.current_user_permissions || []
  return permissions.includes('delete')
})
const deleteNameMatches = computed(() => {
  const expected = (projectStore.currentProject?.title || '').trim()
  return expected.length > 0 && deleteConfirmName.value.trim() === expected
})
const isPublic = computed({
  get: () => projectStore.currentProject?.visibility === 'public',
  set: (value: boolean) => {
    void setProjectVisibility(value ? 'public' : 'private')
  },
})
const memoryAutoSync = computed({
  get: () => componentModels.value[MEMORY_AUTO_SYNC_KEY] !== MEMORY_AUTO_SYNC_DISABLED,
  set: (enabled: boolean) => {
    void setComponentModel(MEMORY_AUTO_SYNC_KEY, enabled ? 'enabled' : MEMORY_AUTO_SYNC_DISABLED)
  },
})

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

function modelOptions(kind: ModelField['kind']) {
  const source =
    kind === 'embedding' ? embeddingModels.value : kind === 'reranker' ? rerankerModels.value : chatModels.value
  return source.map((item) => ({ value: item.id, label: item.name || item.id }))
}

function modelDropdownOptions(kind: ModelField['kind']) {
  return [
    { value: '', label: t('projectSettings.models.default') },
    ...modelOptions(kind),
  ]
}

function freshnessLabel(status: MemoryStatus | null): string {
  const value = String(status?.memory_freshness || status?.status || 'unknown')
  const key = `projectSettings.memory.freshness.${value}`
  const translated = t(key)
  return translated === key ? value : translated
}

async function loadPage() {
  const id = projectId.value
  if (!id) return
  loading.value = true
  try {
    await Promise.all([
      projectStore.fetchProject(id),
      loadModels(),
      refreshMemoryStatus(),
    ])
    componentModels.value = normalizeComponentModels(projectStore.currentProject?.component_models)
  } finally {
    loading.value = false
  }
}

async function loadModels() {
  const [chat, embedding, reranker] = await Promise.all([
    getModels().catch(() => []),
    getEmbeddingModels().catch(() => []),
    getRerankerModels().catch(() => []),
  ])
  chatModels.value = chat
  embeddingModels.value = embedding
  rerankerModels.value = reranker
}

async function refreshMemoryStatus() {
  memoryLoading.value = true
  try {
    memoryStatus.value = await getMemoryStatus(projectId.value)
  } catch {
    memoryStatus.value = null
  } finally {
    memoryLoading.value = false
  }
}

async function persistComponentModels() {
  savingModels.value = true
  try {
    await projectStore.updateProject(projectId.value, { component_models: componentModels.value })
    toast.success(t('projectSettings.models.saved'))
  } catch {
    // interceptor handles toast
  } finally {
    savingModels.value = false
  }
}

async function setComponentModel(key: string, value: string) {
  const normalized = (value || '').trim()
  const next: ComponentModelConfig = { ...componentModels.value }
  if (normalized) {
    next[key] = normalized
  } else {
    delete next[key]
  }
  componentModels.value = next
  await persistComponentModels()
}

function getModelValue(key: string): string {
  return componentModels.value[key] || ''
}

async function handleModelChange(key: string, value: unknown) {
  await setComponentModel(key, String(value || ''))
}

async function pollMemoryTask(taskId: string) {
  const terminal = new Set(['completed', 'failed', 'cancelled'])
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const { task } = await getMemoryTask(projectId.value, taskId)
    if (terminal.has(String(task.status || '').toLowerCase())) {
      return task
    }
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  return null
}

async function handleBuildMemory() {
  memoryBuilding.value = true
  try {
    const { task } = await startMemoryBuildTask(projectId.value, { build_mode: 'rebuild' })
    toast.success(t('projectSettings.memory.buildStarted'))
    const finished = await pollMemoryTask(task.task_id)
    if (finished && String(finished.status).toLowerCase() === 'completed') {
      toast.success(t('projectSettings.memory.buildCompleted'))
    } else if (finished && String(finished.status).toLowerCase() === 'failed') {
      toast.error(finished.error || t('projectSettings.memory.buildFailed'))
    }
    await refreshMemoryStatus()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || t('projectSettings.memory.buildFailed'))
  } finally {
    memoryBuilding.value = false
  }
}

async function handleDeleteMemory() {
  if (!window.confirm(t('projectSettings.memory.deleteConfirm'))) return
  memoryLoading.value = true
  try {
    await deleteProjectMemory(projectId.value)
    toast.success(t('projectSettings.memory.deleted'))
    await refreshMemoryStatus()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || t('projectSettings.memory.deleteFailed'))
  } finally {
    memoryLoading.value = false
  }
}

async function setProjectVisibility(visibility: ProjectVisibility) {
  if (!canManageVisibility.value || savingVisibility.value) return
  if (projectStore.currentProject?.visibility === visibility) return
  savingVisibility.value = true
  try {
    await updateProjectVisibility(projectId.value, visibility)
    await projectStore.fetchProject(projectId.value)
    toast.success(t('projectSettings.visibility.saved'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || t('projectSettings.visibility.failed'))
  } finally {
    savingVisibility.value = false
  }
}

async function handleDownloadBundle() {
  exportingBundle.value = true
  try {
    const blob = await downloadProjectBundle(projectId.value)
    const title = (projectStore.currentProject?.title || 'project').replace(/[^\w.-]+/g, '_')
    downloadBlob(blob, `${title}.zip`)
    toast.success(t('projectSettings.export.success'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || t('projectSettings.export.failed'))
  } finally {
    exportingBundle.value = false
  }
}

function openDeleteModal() {
  if (!canDeleteProject.value) return
  deleteConfirmName.value = ''
  deleteModalOpen.value = true
}

function closeDeleteModal() {
  if (deletingProject.value) return
  deleteModalOpen.value = false
  deleteConfirmName.value = ''
}

async function handleDeleteProject() {
  if (!canDeleteProject.value || !deleteNameMatches.value || deletingProject.value) return
  deletingProject.value = true
  const id = projectId.value
  try {
    await projectStore.deleteProject(id)
    await projectStore.fetchProjects()
    toast.success(t('projectSettings.deleteProject.success'))
    deleteModalOpen.value = false
    await router.push({ name: 'projects' })
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || t('projectSettings.deleteProject.failed'))
  } finally {
    deletingProject.value = false
  }
}

watch(projectId, () => void loadPage(), { immediate: true })
</script>

<template>
  <AppLayout>
    <div class="muse-page muse-page-shell muse-page-shell-standard">
      <header class="muse-page-hero">
        <div class="min-w-0 flex-1 space-y-3">
          <button
            type="button"
            class="inline-flex items-center gap-1 text-xs muse-text-muted transition-colors hover:muse-text-body"
            @click="router.push(`/projects/${projectId}`)"
          >
            <ArrowLeft class="h-3.5 w-3.5" />
            {{ t('projectSettings.backToWorkspace') }}
          </button>
          <div class="flex items-center gap-2">
            <Settings2 class="h-5 w-5 muse-text-muted" />
            <div>
              <h1 class="text-2xl muse-text-title">{{ t('projectSettings.title') }}</h1>
              <p class="mt-2 muse-text-caption">{{ projectTitle }}</p>
            </div>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <Button variant="secondary" @click="router.push(`/projects/${projectId}/skills`)">
            <Sparkles class="mr-1 h-4 w-4" />
            {{ t('projectSkills.title', '项目 Skills') }}
          </Button>
          <Button variant="secondary" @click="router.push(`/projects/${projectId}/versions`)">
            <GitBranch class="mr-1 h-4 w-4" />
            {{ t('versions.title') }}
          </Button>
        </div>
      </header>

      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="muse-spinner" />
      </div>

      <template v-else>
        <section class="muse-page-section">
        <Card v-if="canManageVisibility">
          <div class="mb-4 flex items-center gap-2">
            <Globe2 class="h-4 w-4 muse-text-muted" />
            <h2 class="text-base font-semibold muse-text-heading">{{ t('projectSettings.visibility.title') }}</h2>
          </div>
          <p class="mb-4 text-sm muse-text-muted">{{ t('projectSettings.visibility.subtitle') }}</p>
          <label class="muse-card muse-card-compact flex items-center justify-between gap-3">
            <div>
              <p class="text-sm font-medium muse-text-body">{{ t('projectSettings.visibility.publicLabel') }}</p>
              <p class="mt-0.5 text-xs muse-text-muted">{{ t('projectSettings.visibility.publicHint') }}</p>
            </div>
            <Checkbox v-model="isPublic" :disabled="savingVisibility" />
          </label>
        </Card>

        <Card>
          <h2 class="mb-1 text-base font-semibold muse-text-heading">{{ t('projectSettings.models.title') }}</h2>
          <p class="mb-4 text-sm muse-text-muted">{{ t('projectSettings.models.subtitle') }}</p>

          <div class="space-y-4">
            <div
              v-for="field in MODEL_FIELDS"
              :key="field.key"
              class="grid gap-2 border-b border-[color:var(--muse-border)] pb-4 last:border-b-0 last:pb-0 sm:grid-cols-[minmax(0,1fr)_minmax(220px,280px)] sm:items-center"
            >
              <div>
                <p class="text-sm font-medium muse-text-body">{{ t(field.labelKey) }}</p>
                <p class="mt-0.5 text-xs muse-text-muted">{{ t(field.hintKey) }}</p>
              </div>
              <DropdownSelect
                :model-value="getModelValue(field.key)"
                size="md"
                :disabled="savingModels"
                :aria-label="t(field.labelKey)"
                :options="modelDropdownOptions(field.kind)"
                :placeholder="t('projectSettings.models.default')"
                @update:model-value="handleModelChange(field.key, $event)"
              />
            </div>

            <label class="muse-card muse-card-compact flex items-center justify-between gap-3">
              <div>
                <p class="text-sm font-medium muse-text-body">{{ t('projectSettings.models.autoSync') }}</p>
                <p class="mt-0.5 text-xs muse-text-muted">{{ t('projectSettings.models.autoSyncHint') }}</p>
              </div>
              <Checkbox v-model="memoryAutoSync" :disabled="savingModels" />
            </label>
          </div>
        </Card>

        <Card>
          <div class="mb-4 flex items-center gap-2">
            <Brain class="h-4 w-4 muse-text-muted" />
            <h2 class="text-base font-semibold muse-text-heading">{{ t('projectSettings.memory.title') }}</h2>
          </div>
          <p class="mb-4 text-sm muse-text-muted">{{ t('projectSettings.memory.subtitle') }}</p>

          <div v-if="memoryLoading" class="flex items-center gap-2 text-sm muse-text-muted">
            <Loader2 class="h-4 w-4 animate-spin" />
            {{ t('common.loading') }}
          </div>
          <dl v-else class="mb-4 grid gap-3 sm:grid-cols-2">
            <div>
              <dt class="text-xs uppercase tracking-wide muse-text-faint">{{ t('projectSettings.memory.status') }}</dt>
              <dd class="mt-1 text-sm muse-text-body">{{ memoryStatus?.status || '—' }}</dd>
            </div>
            <div>
              <dt class="text-xs uppercase tracking-wide muse-text-faint">{{ t('projectSettings.memory.freshnessLabel') }}</dt>
              <dd class="mt-1 text-sm muse-text-body">{{ freshnessLabel(memoryStatus) }}</dd>
            </div>
            <div>
              <dt class="text-xs uppercase tracking-wide muse-text-faint">{{ t('projectSettings.memory.lastBuild') }}</dt>
              <dd class="mt-1 text-sm muse-text-body">{{ memoryStatus?.memory_last_build_at || '—' }}</dd>
            </div>
            <div>
              <dt class="text-xs uppercase tracking-wide muse-text-faint">{{ t('projectSettings.memory.memoryId') }}</dt>
              <dd class="mt-1 truncate text-sm font-mono text-xs muse-text-body">{{ memoryStatus?.memory_id || '—' }}</dd>
            </div>
          </dl>

          <div class="flex flex-wrap gap-2">
            <Button variant="primary" :loading="memoryBuilding" @click="handleBuildMemory">
              {{ t('projectSettings.memory.build') }}
            </Button>
            <Button variant="secondary" :disabled="!memoryStatus?.memory_id" @click="handleDeleteMemory">
              {{ t('projectSettings.memory.delete') }}
            </Button>
          </div>
        </Card>

        <Card>
          <div class="mb-4 flex items-center gap-2">
            <Download class="h-4 w-4 muse-text-muted" />
            <h2 class="text-base font-semibold muse-text-heading">{{ t('projectSettings.export.title') }}</h2>
          </div>
          <p class="mb-4 text-sm muse-text-muted">{{ t('projectSettings.export.subtitle') }}</p>
          <Button variant="secondary" :loading="exportingBundle" @click="handleDownloadBundle">
            {{ t('projectSettings.export.downloadBundle') }}
          </Button>
        </Card>

        <Card
          v-if="canDeleteProject"
          class="border-[color:color-mix(in_srgb,var(--muse-danger)_35%,var(--muse-border))] bg-[color:var(--muse-danger-soft)]"
          data-testid="project-delete-danger-zone"
        >
          <div class="mb-4 flex items-center gap-2">
            <Trash2 class="h-4 w-4 text-[color:var(--muse-danger)]" />
            <h2 class="text-base font-semibold text-[color:var(--muse-danger)]">{{ t('projectSettings.deleteProject.title') }}</h2>
          </div>
          <p class="mb-4 text-sm muse-text-muted">{{ t('projectSettings.deleteProject.subtitle') }}</p>
          <Button variant="danger" data-testid="project-delete-open" @click="openDeleteModal">
            {{ t('projectSettings.deleteProject.button') }}
          </Button>
        </Card>
        </section>
      </template>
    </div>

    <Modal
      :show="deleteModalOpen"
      :title="t('projectSettings.deleteProject.modalTitle')"
      @close="closeDeleteModal"
    >
      <p class="mb-4 text-sm muse-text-muted">
        {{ t('projectSettings.deleteProject.modalDescription', { title: projectTitle }) }}
      </p>
      <Input
        v-model="deleteConfirmName"
        :label="t('projectSettings.deleteProject.nameLabel')"
        :placeholder="t('projectSettings.deleteProject.namePlaceholder')"
        :error="deleteConfirmName.trim() && !deleteNameMatches ? t('projectSettings.deleteProject.nameMismatch') : undefined"
        autocomplete="off"
        data-testid="project-delete-name-input"
        @keyup.enter="handleDeleteProject"
      />
      <div class="mt-6 flex flex-wrap justify-end gap-2">
        <Button variant="secondary" :disabled="deletingProject" @click="closeDeleteModal">
          {{ t('projectSettings.deleteProject.cancel') }}
        </Button>
        <Button
          variant="danger"
          :loading="deletingProject"
          :disabled="!deleteNameMatches"
          data-testid="project-delete-confirm"
          @click="handleDeleteProject"
        >
          {{ t('projectSettings.deleteProject.confirm') }}
        </Button>
      </div>
    </Modal>
  </AppLayout>
</template>
