<script setup lang="ts">
import { nextTick, ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Archive, ChevronRight, Loader2, PanelLeftClose, PenLine, Plus, Trash2 } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { useAgentStore } from '@/stores/agent'
import { useAgentLayoutStore } from '@/stores/agentLayout'
import type { AgentSessionSummary } from '@/types'

const props = defineProps<{
  projectId: string
  collapsed: boolean
}>()

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
}>()

const { t } = useI18n()
const agentStore = useAgentStore()
const layoutStore = useAgentLayoutStore()

const orderedSessions = computed(() => agentStore.sessions)

const renamingId = ref<string | null>(null)
const renameValue = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)

function statusDotClass(status: string): string {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'running' || normalized === 'pending') return 'bg-amber-500 animate-pulse'
  if (normalized === 'completed') return 'bg-emerald-500'
  if (normalized === 'failed') return 'bg-red-500'
  if (normalized === 'partial') return 'bg-yellow-500'
  return 'bg-stone-400 dark:bg-zinc-500'
}

function formatRelativeTime(iso: string): string {
  const timestamp = new Date(iso).getTime()
  if (Number.isNaN(timestamp)) return ''
  const diffMs = Date.now() - timestamp
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return t('agent.sidebar.timeJustNow')
  if (minutes < 60) return t('agent.sidebar.timeMinutesAgo', { n: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return t('agent.sidebar.timeHoursAgo', { n: hours })
  const days = Math.floor(hours / 24)
  if (days < 7) return t('agent.sidebar.timeDaysAgo', { n: days })
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function sessionLabel(session: AgentSessionSummary): string {
  return session.title?.trim() || t('agent.sidebar.untitledTask')
}

function handleSelect(session: AgentSessionSummary) {
  if (renamingId.value === session.session_id) return
  void agentStore.selectSession(props.projectId, session.session_id)
}

function handleArchive(session: AgentSessionSummary) {
  void agentStore.archiveSession(props.projectId, session.session_id)
}

function handleDelete(session: AgentSessionSummary) {
  void agentStore.deleteSession(props.projectId, session.session_id)
}

function handleNew() {
  agentStore.startNewSession()
}

function expandSidebar() {
  emit('update:collapsed', false)
}

function collapseSidebar() {
  emit('update:collapsed', true)
}

function startRename(session: AgentSessionSummary) {
  renamingId.value = session.session_id
  renameValue.value = session.title?.trim() || ''
  nextTick(() => {
    renameInputRef.value?.focus()
    renameInputRef.value?.select()
  })
}

async function commitRename(session: AgentSessionSummary) {
  const newTitle = renameValue.value.trim()
  renamingId.value = null
  if (newTitle === (session.title?.trim() || '')) return
  try {
    await agentStore.renameSession(props.projectId, session.session_id, newTitle)
  } catch {
    // keep existing title on failure
  }
}

function cancelRename() {
  renamingId.value = null
}
</script>

<template>
  <aside
    data-testid="agent-session-sidebar"
    :class="cn(
      layoutStore.isColumnResizing ? 'muse-workspace-sidebar' : 'muse-workspace-sidebar transition-[width] duration-200',
      collapsed ? 'muse-workspace-sidebar-collapsed' : 'muse-workspace-sidebar-expanded'
    )"
  >
    <div v-if="collapsed" class="flex flex-col items-center gap-1 py-2">
      <button
        type="button"
        data-testid="agent-sidebar-expand"
        class="muse-icon-btn"
        :aria-label="t('agent.sidebar.expandSidebar')"
        :title="t('agent.sidebar.expandSidebar')"
        @click="expandSidebar"
      >
        <ChevronRight class="h-4 w-4" />
      </button>
      <button
        type="button"
        data-testid="agent-new-session"
        class="muse-icon-btn"
        :aria-label="t('agent.sidebar.newAgent')"
        @click="handleNew"
      >
        <Plus class="h-4 w-4" />
      </button>
    </div>

    <template v-else>
      <div class="muse-workspace-sidebar-header">
        <h2 class="muse-text-overline">{{ t('agent.sidebar.title') }}</h2>
        <button
          type="button"
          data-testid="agent-sidebar-collapse"
          class="muse-icon-btn !h-7 !w-7"
          :aria-label="t('agent.sidebar.collapseSidebar')"
          :title="t('agent.sidebar.collapseSidebar')"
          @click="collapseSidebar"
        >
          <PanelLeftClose class="h-3.5 w-3.5" />
        </button>
      </div>

      <div class="flex min-h-0 flex-1 flex-col">
        <div class="muse-workspace-sidebar-body">
          <button
            type="button"
            data-testid="agent-new-session"
            class="muse-workspace-new-agent-btn muse-focus-ring"
            @click="handleNew"
          >
            <Plus class="h-3.5 w-3.5" />
            {{ t('agent.sidebar.newAgent') }}
          </button>
        </div>

        <div class="muse-workspace-list space-y-1" data-testid="agent-session-list">
          <div v-if="agentStore.sessionsLoading && !orderedSessions.length" class="flex justify-center py-8">
            <Loader2 class="h-4 w-4 animate-spin muse-text-faint" />
          </div>

          <p
            v-else-if="!orderedSessions.length"
            class="px-2 py-8 text-center text-xs muse-text-faint"
          >
            {{ t('agent.sidebar.noSessions') }}
          </p>

          <div
            v-for="session in orderedSessions"
            :key="session.session_id"
            :data-testid="`agent-session-item-${session.session_id}`"
            :class="cn(
              'muse-workspace-list-item group',
              agentStore.currentSessionId === session.session_id && 'muse-workspace-list-item-active'
            )"
            @click="handleSelect(session)"
          >
            <span
              :class="cn('h-2 w-2 shrink-0 rounded-full', statusDotClass(session.status))"
              aria-hidden="true"
            />
            <div class="min-w-0 flex-1">
              <input
                v-if="renamingId === session.session_id"
                ref="renameInputRef"
                v-model="renameValue"
                type="text"
                class="muse-input w-full py-0.5 text-xs"
                :placeholder="t('agent.sidebar.untitledTask')"
                @keydown.enter="commitRename(session)"
                @keydown.esc="cancelRename"
                @blur="commitRename(session)"
                @click.stop
              />
              <template v-else>
                <p class="truncate text-xs font-medium muse-text-body">
                  {{ sessionLabel(session) }}
                </p>
                <p class="truncate text-[11px] muse-text-faint">
                  {{ formatRelativeTime(session.updated_at) }}
                </p>
              </template>
            </div>
            <div class="hidden shrink-0 items-center gap-0.5 group-hover:flex">
              <button
                v-if="renamingId !== session.session_id"
                type="button"
                class="muse-icon-btn"
                :aria-label="t('agent.sidebar.renameSession')"
                :title="t('agent.sidebar.renameSession')"
                @click.stop="startRename(session)"
              >
                <PenLine class="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                class="muse-icon-btn"
                :aria-label="t('agent.sidebar.archiveSession')"
                @click.stop="handleArchive(session)"
              >
                <Archive class="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                class="muse-icon-btn hover:bg-[color:var(--muse-danger-soft)] hover:text-[color:var(--muse-danger)]"
                :aria-label="t('agent.sidebar.deleteSession')"
                @click.stop="handleDelete(session)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </aside>
</template>
