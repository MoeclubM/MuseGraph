<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Settings2 } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import AgentSessionSidebar from '@/components/agent/AgentSessionSidebar.vue'
import AgentCenterPanel from '@/components/agent/AgentCenterPanel.vue'
import AgentBrowserPanel from '@/components/agent/AgentBrowserPanel.vue'
import AgentResizeHandle from '@/components/agent/AgentResizeHandle.vue'
import { useAgentStore } from '@/stores/agent'
import { useAgentLayoutStore, CENTER_PANEL_MIN_WIDTH } from '@/stores/agentLayout'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const { t } = useI18n()
const projectStore = useProjectStore()
const agentStore = useAgentStore()
const layoutStore = useAgentLayoutStore()

const projectId = computed(() => String(route.params.id || ''))

const projectTitle = computed(() => projectStore.currentProject?.title || t('agent.workspace.loadingProject'))

async function initialize(id: string) {
  if (!id) return
  layoutStore.bindProject(id)
  agentStore.reset()
  await Promise.all([
    projectStore.fetchProject(id).catch(() => {}),
    agentStore.loadSessions(id).catch(() => {}),
    agentStore.loadModels().catch(() => {}),
  ])
  agentStore.applyDefaultModel(projectStore.currentProject)
}

watch(projectId, (id) => void initialize(id), { immediate: true })

const sessionStatus = computed(() => String(agentStore.currentSession?.status || '').toLowerCase())
watch(sessionStatus, (next, prev) => {
  const wasRunning = prev === 'running' || prev === 'pending'
  const isTerminal = ['completed', 'failed', 'partial'].includes(next)
  if (wasRunning && isTerminal) {
    void projectStore.fetchProject(projectId.value).catch(() => {})
  }
})

function onSidebarCollapsedChange(collapsed: boolean) {
  layoutStore.setSidebarCollapsed(collapsed)
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'b') return
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
  event.preventDefault()
  layoutStore.toggleSidebarCollapsed()
}

onMounted(() => {
  window.addEventListener('keydown', onGlobalKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  agentStore.stopLiveUpdates()
})
</script>

<template>
  <AppLayout :padded="false">
    <div class="muse-workspace-shell" :class="{ 'muse-column-resizing': layoutStore.isColumnResizing }">
      <div class="muse-workspace-toolbar">
        <p class="min-w-0 flex-1 truncate text-xs font-medium muse-text-body">
          <span class="muse-text-faint">{{ t('common.projects') }}</span>
          <span class="mx-1.5 muse-text-faint">/</span>
          {{ projectTitle }}
        </p>
        <router-link
          :to="`/projects/${projectId}/settings`"
          class="muse-nav-rail-item ml-auto"
          :title="t('nav.settings')"
          data-testid="agent-nav-settings"
        >
          <Settings2 class="h-4 w-4" />
        </router-link>
      </div>

      <div class="flex min-h-0 flex-1">
        <div class="flex min-h-0 min-w-0 flex-1">
          <AgentSessionSidebar
            :style="{ flex: '0 0 auto', width: layoutStore.sidebarWidthStyle() }"
            :collapsed="layoutStore.sidebarCollapsed"
            :project-id="projectId"
            @update:collapsed="onSidebarCollapsedChange"
          />
          <AgentResizeHandle
            left="sessions"
            right="center"
            @resize="(delta) => layoutStore.resizeSidebar(delta)"
          />
          <AgentCenterPanel
            :project-id="projectId"
            :style="{ flex: '1 1 0%', minWidth: `${CENTER_PANEL_MIN_WIDTH}px` }"
          />
          <AgentResizeHandle
            left="center"
            right="browser"
            @resize="(delta) => layoutStore.resizeBrowser(delta)"
          />
          <AgentBrowserPanel
            :project-id="projectId"
            :style="{ flex: '0 0 auto', width: layoutStore.browserWidthStyle() }"
          />
        </div>
      </div>
    </div>
  </AppLayout>
</template>
