<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertCircle, CheckCircle, Clock, Loader2, Search, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import {
  getMemoryStatus,
  searchProjectMemory,
  deleteProjectMemory,
  type MemoryStatus,
} from '@/api/memory'
import SearchInput from '@/components/ui/SearchInput.vue'
import type { AgentWorkspace } from '@/types'

const props = defineProps<{
  projectId: string
  workspace: AgentWorkspace
}>()

const { t } = useI18n()

const memoryStatus = ref<MemoryStatus | null>(null)
const memoryStatusLoading = ref(false)
const memoryStatusError = ref<string | null>(null)

const searchQuery = ref('')
const searchLoading = ref(false)
const searchError = ref<string | null>(null)
const searchResults = ref<Record<string, unknown> | null>(null)

const deleteConfirming = ref(false)
const deleteLoading = ref(false)

const structuredMemory = computed(() =>
  props.workspace.structured_memory && typeof props.workspace.structured_memory === 'object'
    ? props.workspace.structured_memory
    : {},
)

const memorySchema = computed(() =>
  props.workspace.memory_schema && typeof props.workspace.memory_schema === 'object'
    ? props.workspace.memory_schema
    : {},
)

const memoryStatusLabel = (status: string): string => {
  const key = `agent.memory.freshness.${status}`
  const translated = t(key)
  return translated === key ? status : translated
}

const memoryStatusIcon = (status: string) => {
  switch (status) {
    case 'fresh':
      return CheckCircle
    case 'stale':
      return AlertCircle
    case 'syncing':
      return Loader2
    default:
      return Clock
  }
}

const memoryStatusColor = (status: string): string => {
  switch (status) {
    case 'fresh':
      return 'text-green-500'
    case 'stale':
      return 'text-yellow-500'
    case 'syncing':
      return 'text-blue-500'
    default:
      return 'text-gray-500'
  }
}

async function loadMemoryStatus() {
  if (!props.projectId) return
  memoryStatusLoading.value = true
  memoryStatusError.value = null
  try {
    memoryStatus.value = await getMemoryStatus(props.projectId)
  } catch (error) {
    memoryStatus.value = null
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    memoryStatusError.value =
      detail || (error instanceof Error ? error.message : t('agent.memory.loadStatusFailed'))
  } finally {
    memoryStatusLoading.value = false
  }
}

async function handleSearch() {
  const query = searchQuery.value.trim()
  if (!query) {
    searchResults.value = null
    searchError.value = null
    return
  }

  searchLoading.value = true
  searchError.value = null
  try {
    searchResults.value = await searchProjectMemory(props.projectId, query)
  } catch (error) {
    searchResults.value = null
    searchError.value = error instanceof Error ? error.message : t('agent.memory.searchFailed')
  } finally {
    searchLoading.value = false
  }
}

async function handleDeleteMemory() {
  if (!deleteConfirming.value) {
    deleteConfirming.value = true
    return
  }

  deleteLoading.value = true
  try {
    await deleteProjectMemory(props.projectId)
    memoryStatus.value = null
    searchResults.value = null
    deleteConfirming.value = false
  } catch (error) {
    const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
    throw new Error(detail || (error instanceof Error ? error.message : t('agent.memory.deleteFailed')))
  } finally {
    deleteLoading.value = false
  }
}

function formatBuildTime(dateString: string | null | undefined): string {
  if (!dateString) return '—'
  try {
    const date = new Date(dateString)
    return date.toLocaleString()
  } catch {
    return dateString
  }
}

const searchResultEntries = computed(() => {
  if (!searchResults.value) return []
  return Object.entries(searchResults.value).filter(([key, value]) => {
    return value !== null && value !== undefined && value !== ''
  })
})

watch(
  () => props.projectId,
  () => {
    void loadMemoryStatus()
  },
  { immediate: true },
)

defineExpose({ reload: loadMemoryStatus })
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col" data-testid="agent-memory-panel">
    <div class="border-b border-[color:var(--muse-border)] p-3">
      <h3 class="text-sm font-semibold muse-text-heading">{{ t('agent.memory.title') }}</h3>
      <p class="mt-1 text-[11px] muse-text-faint">{{ t('agent.memory.subtitle') }}</p>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto muse-workspace-scroll">
      <!-- Memory Status Section -->
      <section class="border-b border-[color:var(--muse-border)] p-3">
        <div class="mb-2 flex items-center justify-between gap-2">
          <h4 class="text-xs font-semibold muse-text-heading">{{ t('agent.memory.statusTitle') }}</h4>
          <button
            type="button"
            class="muse-btn muse-btn-secondary shrink-0 px-2"
            :disabled="memoryStatusLoading"
            @click="loadMemoryStatus"
          >
            <Loader2 v-if="memoryStatusLoading" class="h-3.5 w-3.5 animate-spin" />
            <span v-else>{{ t('agent.memory.refresh') }}</span>
          </button>
        </div>

        <div v-if="memoryStatusLoading" class="text-[11px] muse-text-muted">
          {{ t('common.loading') }}
        </div>
        <div v-else-if="memoryStatusError" class="text-[11px] text-[color:var(--muse-danger)]">
          {{ memoryStatusError }}
        </div>
        <div v-else-if="!memoryStatus" class="text-[11px] muse-text-faint">
          {{ t('agent.memory.noStatus') }}
        </div>
        <div v-else class="space-y-2">
          <div class="flex items-center gap-2">
            <component
              :is="memoryStatusIcon(memoryStatus.memory_freshness || 'empty')"
              :class="cn('h-4 w-4', memoryStatusColor(memoryStatus.memory_freshness || 'empty'), memoryStatus.memory_freshness === 'syncing' && 'animate-spin')"
            />
            <span class="text-xs font-medium muse-text-heading">
              {{ memoryStatusLabel(memoryStatus.memory_freshness || 'empty') }}
            </span>
          </div>

          <div class="grid grid-cols-2 gap-2 text-[11px]">
            <div class="rounded border border-[color:var(--muse-border)] p-2">
              <div class="font-medium muse-text-heading">{{ t('agent.memory.memoryId') }}</div>
              <div class="mt-1 truncate muse-text-muted">{{ memoryStatus.memory_id || '—' }}</div>
            </div>
            <div class="rounded border border-[color:var(--muse-border)] p-2">
              <div class="font-medium muse-text-heading">{{ t('agent.memory.lastBuild') }}</div>
              <div class="mt-1 muse-text-muted">{{ formatBuildTime(memoryStatus.memory_last_build_at) }}</div>
            </div>
            <div class="rounded border border-[color:var(--muse-border)] p-2">
              <div class="font-medium muse-text-heading">{{ t('agent.memory.textType') }}</div>
              <div class="mt-1 muse-text-muted">{{ memoryStatus.text_type || '—' }}</div>
            </div>
            <div class="rounded border border-[color:var(--muse-border)] p-2">
              <div class="font-medium muse-text-heading">{{ t('agent.memory.memoryMode') }}</div>
              <div class="mt-1 muse-text-muted">{{ memoryStatus.memory_mode || '—' }}</div>
            </div>
          </div>

          <div class="flex gap-2">
            <button
              type="button"
              class="muse-btn muse-btn-danger shrink-0 px-2"
              :disabled="deleteLoading"
              @click="handleDeleteMemory"
            >
              <Loader2 v-if="deleteLoading" class="h-3.5 w-3.5 animate-spin" />
              <span v-else>{{ deleteConfirming ? t('agent.memory.confirmDelete') : t('agent.memory.delete') }}</span>
            </button>
            <button
              v-if="deleteConfirming"
              type="button"
              class="muse-btn muse-btn-secondary shrink-0 px-2"
              @click="deleteConfirming = false"
            >
              {{ t('common.cancel') }}
            </button>
          </div>
        </div>
      </section>

      <!-- Search Section -->
      <section class="border-b border-[color:var(--muse-border)] p-3">
        <h4 class="mb-2 text-xs font-semibold muse-text-heading">{{ t('agent.memory.searchTitle') }}</h4>
        <div class="flex gap-2">
          <SearchInput
            v-model="searchQuery"
            :placeholder="t('agent.memory.searchPlaceholder')"
            :aria-label="t('agent.memory.searchAriaLabel')"
            test-id="agent-memory-search-input"
            @search="handleSearch"
          />
          <button
            type="button"
            class="muse-btn muse-btn-secondary shrink-0 px-2"
            :disabled="searchLoading"
            data-testid="agent-memory-search-button"
            @click="handleSearch"
          >
            <Loader2 v-if="searchLoading" class="h-3.5 w-3.5 animate-spin" />
            <Search v-else class="h-3.5 w-3.5" />
          </button>
          <button
            v-if="searchQuery"
            type="button"
            class="muse-btn muse-btn-secondary shrink-0 px-2"
            @click="searchQuery = ''; searchResults = null; searchError = null"
          >
            <X class="h-3.5 w-3.5" />
          </button>
        </div>
        <p v-if="searchError" class="mt-2 text-[11px] text-[color:var(--muse-danger)]">{{ searchError }}</p>
      </section>

      <!-- Search Results -->
      <section v-if="searchResults" class="border-b border-[color:var(--muse-border)] p-3">
        <h4 class="mb-2 text-xs font-semibold muse-text-heading">
          {{ t('agent.memory.searchResults') }}
          <span class="ml-1 text-[10px] font-normal muse-text-faint">({{ searchResultEntries.length }})</span>
        </h4>
        <div v-if="!searchResultEntries.length" class="text-[11px] muse-text-faint">
          {{ t('agent.memory.noSearchResults') }}
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="[key, value] in searchResultEntries"
            :key="key"
            class="rounded border border-[color:var(--muse-border)] p-2"
          >
            <div class="text-xs font-medium muse-text-heading">{{ key }}</div>
            <div class="mt-1 text-[11px] muse-text-muted line-clamp-4">
              {{ typeof value === 'object' ? JSON.stringify(value, null, 2) : value }}
            </div>
          </div>
        </div>
      </section>

      <!-- Structured Memory Section -->
      <section class="p-3">
        <h4 class="mb-2 text-xs font-semibold muse-text-heading">{{ t('agent.memory.structuredTitle') }}</h4>
        <div v-if="!Object.keys(structuredMemory).length" class="text-[11px] muse-text-faint">
          {{ t('agent.memory.noStructuredMemory') }}
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="(value, key) in structuredMemory"
            :key="key"
            class="rounded border border-[color:var(--muse-border)] p-2"
          >
            <div class="text-xs font-medium muse-text-heading">{{ key }}</div>
            <div class="mt-1 text-[11px] muse-text-muted line-clamp-6">
              {{ typeof value === 'object' ? JSON.stringify(value, null, 2) : value }}
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>