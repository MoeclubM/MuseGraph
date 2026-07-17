<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { GitBranch, Loader2, RotateCcw, Save } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { useToast } from '@/composables/useToast'
import {
  createProjectRecordPoint,
  getProjectVersionHistory,
  restoreProjectRecordPoint,
  type ProjectRecordPoint,
  type ProjectVersionHistory,
} from '@/api/projectVersions'

const props = defineProps<{
  projectId: string
}>()

const { t } = useI18n()
const toast = useToast()

const loading = ref(true)
const history = ref<ProjectVersionHistory | null>(null)
const snapshotMessage = ref('')
const creating = ref(false)
const restoringId = ref('')

const recordPoints = computed(() => history.value?.record_points || [])
const currentRecordPoint = computed(() => history.value?.current_record_point || null)

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const now = Date.now()
  const diff = now - date.getTime()
  if (diff < 60000) return t('versions.justNow')
  if (diff < 3600000) return t('versions.minutesAgo', { n: Math.floor(diff / 60000) })
  if (diff < 86400000) return t('versions.hoursAgo', { n: Math.floor(diff / 3600000) })
  return date.toLocaleDateString()
}

async function loadHistory() {
  if (!props.projectId) return
  loading.value = true
  try {
    history.value = await getProjectVersionHistory(props.projectId)
  } catch {
    history.value = null
  } finally {
    loading.value = false
  }
}

async function handleCreateSnapshot() {
  const message = snapshotMessage.value.trim()
  if (!message || creating.value) return
  creating.value = true
  try {
    history.value = await createProjectRecordPoint(props.projectId, message)
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
    history.value = await restoreProjectRecordPoint(props.projectId, point.id)
    toast.success(t('versions.restoreSuccess'))
  } catch (error) {
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    toast.error(detail || t('versions.restoreFailed'))
  } finally {
    restoringId.value = ''
  }
}

watch(() => props.projectId, () => void loadHistory(), { immediate: true })
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-hidden">
    <div class="muse-workspace-bar flex items-center gap-2">
      <GitBranch class="h-4 w-4 muse-text-accent" />
      <span class="text-xs font-semibold muse-text-heading">{{ t('versions.title') }}</span>
    </div>

    <div class="muse-workspace-scroll min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      <!-- Create snapshot -->
      <div class="muse-card p-3">
        <p class="mb-2 text-[11px] muse-text-faint">{{ t('versions.createSnapshotHint') }}</p>
        <div class="flex flex-col gap-2">
          <input
            v-model="snapshotMessage"
            type="text"
            class="muse-input text-xs"
            :placeholder="t('versions.snapshotPlaceholder')"
            data-testid="version-snapshot-input"
            @keydown.enter="handleCreateSnapshot"
          />
          <button
            class="muse-btn-primary flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-50"
            :disabled="!snapshotMessage.trim() || creating"
            data-testid="version-snapshot-create"
            @click="handleCreateSnapshot"
          >
            <Loader2 v-if="creating" class="h-3 w-3 animate-spin" />
            <Save v-else class="h-3 w-3" />
            {{ t('versions.createSnapshot') }}
          </button>
        </div>
      </div>

      <!-- History list -->
      <div>
        <div class="mb-2 flex items-center justify-between">
          <span class="text-[11px] font-semibold muse-text-heading">{{ t('versions.history') }}</span>
          <Loader2 v-if="loading" class="h-3 w-3 animate-spin muse-text-faint" />
        </div>

        <p v-if="!loading && !recordPoints.length" class="text-xs muse-text-muted">
          {{ t('versions.empty') }}
        </p>

        <ul v-else class="space-y-1.5" data-testid="version-history-list">
          <li
            v-for="point in recordPoints"
            :key="point.id"
            class="group flex items-center justify-between gap-2 rounded-md border border-[color:var(--muse-border)] px-2.5 py-2 transition-colors hover:bg-[color:var(--muse-field)]"
            :data-testid="`version-item-${point.id}`"
          >
            <div class="min-w-0 flex-1">
              <p class="truncate text-xs font-medium muse-text-body">{{ point.label }}</p>
              <p class="text-[10px] muse-text-faint">{{ formatDate(point.created_at) }}</p>
              <p
                v-if="currentRecordPoint === point.id"
                class="mt-0.5 text-[9px] font-semibold uppercase tracking-wide muse-text-accent"
              >
                {{ t('versions.current') }}
              </p>
            </div>
            <button
              class="shrink-0 rounded-md border border-[color:var(--muse-border)] px-2 py-1 text-[10px] font-medium muse-text-muted transition-colors hover:bg-[color:var(--muse-field)] hover:muse-text-body disabled:opacity-40"
              :disabled="restoringId === point.id || currentRecordPoint === point.id"
              :data-testid="`version-restore-${point.id}`"
              @click="handleRestore(point)"
            >
              <Loader2 v-if="restoringId === point.id" class="mr-1 inline h-2.5 w-2.5 animate-spin" />
              <RotateCcw v-else class="mr-1 inline h-2.5 w-2.5" />
              {{ t('versions.restore') }}
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
