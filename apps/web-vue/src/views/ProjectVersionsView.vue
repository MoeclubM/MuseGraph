<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, GitBranch, Loader2, RotateCcw, Save } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { useProjectStore } from '@/stores/project'
import { useToast } from '@/composables/useToast'
import {
  createProjectRecordPoint,
  getProjectVersionHistory,
  restoreProjectRecordPoint,
  type ProjectRecordPoint,
  type ProjectVersionHistory,
} from '@/api/projectVersions'

const route = useRoute()
const { t } = useI18n()
const projectStore = useProjectStore()
const toast = useToast()

const projectId = computed(() => String(route.params.id || ''))
const loading = ref(true)
const history = ref<ProjectVersionHistory | null>(null)
const snapshotMessage = ref('')
const creating = ref(false)
const restoringId = ref('')

const projectTitle = computed(() => projectStore.currentProject?.title || t('versions.loadingProject'))
const recordPoints = computed(() => history.value?.record_points || [])
const currentRecordPoint = computed(() => history.value?.current_record_point || null)

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString()
}

async function loadHistory() {
  const id = projectId.value
  if (!id) return
  loading.value = true
  try {
    await projectStore.fetchProject(id).catch(() => {})
    history.value = await getProjectVersionHistory(id)
  } catch (error) {
    history.value = null
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    toast.error(detail || t('versions.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function handleCreateSnapshot() {
  const message = snapshotMessage.value.trim()
  if (!message || creating.value) return
  creating.value = true
  try {
    history.value = await createProjectRecordPoint(projectId.value, message)
    snapshotMessage.value = ''
    toast.success(t('versions.snapshotCreated'))
  } catch (error) {
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    toast.error(detail || t('versions.snapshotFailed'))
  } finally {
    creating.value = false
  }
}

async function handleRestore(point: ProjectRecordPoint) {
  if (restoringId.value) return
  const confirmed = window.confirm(t('versions.restoreConfirm', { label: point.label }))
  if (!confirmed) return
  restoringId.value = point.id
  try {
    history.value = await restoreProjectRecordPoint(projectId.value, point.id)
    await projectStore.fetchProject(projectId.value)
    toast.success(t('versions.restoreSuccess'))
  } catch (error) {
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    toast.error(detail || t('versions.restoreFailed'))
  } finally {
    restoringId.value = ''
  }
}

watch(projectId, () => void loadHistory(), { immediate: true })
</script>

<template>
  <AppLayout>
    <div class="mx-auto max-w-3xl space-y-6 py-6">
      <div class="flex items-center gap-3">
        <router-link
          :to="`/projects/${projectId}`"
          class="flex items-center gap-1 text-sm muse-text-muted transition-colors hover:muse-text-body"
        >
          <ArrowLeft class="h-4 w-4" />
          {{ t('versions.backToWorkspace') }}
        </router-link>
      </div>

      <div class="flex items-start gap-3">
        <GitBranch class="mt-1 h-5 w-5 muse-text-accent" />
        <div>
          <h1 class="text-xl font-semibold muse-text-heading">{{ t('versions.title') }}</h1>
          <p class="mt-1 text-sm muse-text-muted">{{ projectTitle }}</p>
          <p class="mt-2 text-xs muse-text-faint">{{ t('versions.subtitle') }}</p>
        </div>
      </div>

      <Card class="p-4">
        <h2 class="text-sm font-semibold muse-text-heading">{{ t('versions.createSnapshot') }}</h2>
        <p class="mt-1 text-xs muse-text-faint">{{ t('versions.createSnapshotHint') }}</p>
        <div class="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            v-model="snapshotMessage"
            type="text"
            class="muse-input flex-1"
            :placeholder="t('versions.snapshotPlaceholder')"
            data-testid="version-snapshot-input"
            @keydown.enter="handleCreateSnapshot"
          />
          <Button
            :disabled="!snapshotMessage.trim() || creating"
            data-testid="version-snapshot-create"
            @click="handleCreateSnapshot"
          >
            <Loader2 v-if="creating" class="mr-1 h-4 w-4 animate-spin" />
            <Save v-else class="mr-1 h-4 w-4" />
            {{ t('versions.createSnapshot') }}
          </Button>
        </div>
      </Card>

      <Card class="p-4">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold muse-text-heading">{{ t('versions.history') }}</h2>
          <Loader2 v-if="loading" class="h-4 w-4 animate-spin muse-text-faint" />
        </div>

        <p v-if="!loading && !recordPoints.length" class="mt-4 text-sm muse-text-muted">
          {{ t('versions.empty') }}
        </p>

        <ul v-else class="mt-4 space-y-2" data-testid="version-history-list">
          <li
            v-for="point in recordPoints"
            :key="point.id"
            class="flex items-center justify-between gap-3 rounded-md border border-[color:var(--muse-border)] px-3 py-2"
            :data-testid="`version-item-${point.id}`"
          >
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium muse-text-body">{{ point.label }}</p>
              <p class="text-[11px] muse-text-faint">{{ formatDate(point.created_at) }}</p>
              <p
                v-if="currentRecordPoint === point.id"
                class="mt-1 text-[10px] font-medium uppercase tracking-wide muse-text-accent"
              >
                {{ t('versions.current') }}
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              :disabled="restoringId === point.id || currentRecordPoint === point.id"
              :data-testid="`version-restore-${point.id}`"
              @click="handleRestore(point)"
            >
              <Loader2 v-if="restoringId === point.id" class="mr-1 h-3.5 w-3.5 animate-spin" />
              <RotateCcw v-else class="mr-1 h-3.5 w-3.5" />
              {{ t('versions.restore') }}
            </Button>
          </li>
        </ul>
      </Card>
    </div>
  </AppLayout>
</template>
