<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft,
  Loader2,
  Paperclip,
  SendHorizontal,
  Sparkles,
  Square,
  X,
} from '@lucide/vue'
 import RichMessageBubble from '@/components/agent/RichMessageBubble.vue'
 import Button from '@/components/ui/Button.vue'
 import DropdownSelect from '@/components/ui/DropdownSelect.vue'
 import FileMentionPopup from '@/components/agent/FileMentionPopup.vue'
import SlashCommandPopup from '@/components/agent/SlashCommandPopup.vue'
 import { useAgentStore } from '@/stores/agent'
 import { listSkills, type SkillItem } from '@/api/skills'
import { listProjectFiles, type ProjectFile } from '@/api/projectFiles'
 import type { AgentMessage, AgentStep } from '@/types'

 const props = defineProps<{
   projectId: string
 }>()

 const { t } = useI18n()
 const agentStore = useAgentStore()

const draft = ref('')
const inputEl = ref<HTMLTextAreaElement | null>(null)
const timelineEl = ref<HTMLDivElement | null>(null)
const fileInputEl = ref<HTMLInputElement | null>(null)
const attachedFiles = ref<File[]>([])

// ----- Skill picker (@-mention) state -----
const skills = ref<SkillItem[]>([])
const pickedSkillSlug = ref<string | null>(null)

// ----- File picker (@-mention) state -----
const projectFiles = ref<ProjectFile[]>([])
const filePopup = ref<InstanceType<typeof FileMentionPopup> | null>(null)
const fileMentionVisible = ref(false)
const fileMentionQuery = ref('')
const fileMentionPos = ref({ bottom: 0, left: 0 })

// ----- Slash command (/) state -----
type SlashMode = 'menu' | 'skill' | 'model' | 'effort' | null
const slashMode = ref<SlashMode>(null)
const slashPopup = ref<InstanceType<typeof SlashCommandPopup> | null>(null)
const slashVisible = ref(false)
const slashQuery = ref('')
const slashPos = ref({ bottom: 0, left: 0 })
const pickedEffort = ref<string | null>(null)

const slashMenuItems = [
  { id: 'skill', label: 'Skill', desc: '选择创作 skill' },
  { id: 'model', label: 'Model', desc: '切换模型' },
  { id: 'effort', label: 'Effort', desc: '切换思考强度' },
]

const effortOptions = [
  { id: 'none', label: 'None', desc: '不启用思考' },
  { id: 'minimal', label: 'Minimal', desc: '最低强度' },
  { id: 'low', label: 'Low', desc: '低强度' },
  { id: 'medium', label: 'Medium', desc: '中等强度' },
  { id: 'high', label: 'High', desc: '高强度' },
]

const activeSkillFromSession = computed<string | null>(() => {
  const ws = (agentStore.currentSession as any)?.agent_workspace
  if (ws && typeof ws === 'object' && typeof ws.active_skill_slug === 'string') {
    return ws.active_skill_slug || null
  }
  return null
})

const effectiveSkillSlug = computed<string | null>(
  () => pickedSkillSlug.value || activeSkillFromSession.value,
)

async function refreshSkills() {
  if (!props.projectId) return
  try {
    skills.value = await listSkills(props.projectId, 'chat')
  } catch {
    // surfacing this in the chat would be noisy; settings page is the source of truth
  }
}

async function refreshProjectFiles() {
  try {
    projectFiles.value = await listProjectFiles(props.projectId)
  } catch {
    // non-critical; file mention just won't show results
  }
}

onMounted(refreshSkills)
onMounted(refreshProjectFiles)
watch(() => props.projectId, () => {
  pickedSkillSlug.value = null
  void refreshSkills()
  void refreshProjectFiles()
})

// ---------- Turn-based grouping ----------

const messages = computed<AgentMessage[]>(() => agentStore.currentSession?.messages || [])
const steps = computed<AgentStep[]>(() => agentStore.currentSession?.steps || [])

/**
 * Build a flat, chronologically-ordered list of "turn items".
 * Each turn starts with a user message, followed by steps & agent messages
 * that belong to it (steps injected near the turn's user message).
 */
interface TurnItem {
  kind: 'user' | 'agent' | 'step'
  message?: AgentMessage
  step?: AgentStep
  /** Sequential turn number (1-based); 0 for items before the first user message */
  turn: number
}

const turnItems = computed<TurnItem[]>(() => {
  const msgs = messages.value
  const stps = steps.value

  type Tagged =
    | { kind: 'message'; message: AgentMessage; ts: number }
    | { kind: 'step'; step: AgentStep; ts: number }

  const parseTs = (iso?: string) => {
    if (!iso) return Number.MAX_SAFE_INTEGER
    const t = Date.parse(iso)
    return Number.isNaN(t) ? Number.MAX_SAFE_INTEGER : t
  }

  const tagged: Tagged[] = []
  for (const msg of msgs) {
    tagged.push({ kind: 'message', message: msg, ts: parseTs(msg.created_at) })
  }
  for (const step of stps) {
    tagged.push({ kind: 'step', step, ts: parseTs(step.created_at) })
  }
  tagged.sort((a, b) => a.ts - b.ts)

  let currentTurn = 0
  const items: TurnItem[] = []
  for (const entry of tagged) {
    if (entry.kind === 'message') {
      if (entry.message.role === 'user') currentTurn++
      items.push({
        kind: entry.message.role === 'user' ? 'user' : 'agent',
        message: entry.message,
        turn: currentTurn,
      })
    } else {
      items.push({ kind: 'step', step: entry.step, turn: currentTurn })
    }
  }
  return items
})

const sessionTitle = computed(
  () =>
    agentStore.currentSession?.title?.trim()
    || (agentStore.currentSessionId ? t('agent.center.untitledTask') : t('agent.center.newTask'))
)

const sessionStatus = computed(() => String(agentStore.currentSession?.status || '').toLowerCase())

const statusMessageKeys = {
  running: 'agent.center.status.running',
  pending: 'agent.center.status.pending',
  completed: 'agent.center.status.completed',
  failed: 'agent.center.status.failed',
  partial: 'agent.center.status.partial',
} as const

const sessionStatusLabel = computed(() => {
  const key = sessionStatus.value as keyof typeof statusMessageKeys
  return statusMessageKeys[key] ? t(statusMessageKeys[key]) : sessionStatus.value
})

const statusDotClass = computed(() => {
  switch (sessionStatus.value) {
    case 'running':
    case 'pending':
      return 'bg-amber-500'
    case 'completed':
      return 'bg-emerald-500'
    case 'failed':
      return 'bg-red-500'
    case 'partial':
      return 'bg-yellow-500'
    default:
      return 'bg-[color:var(--muse-text-faint)]'
  }
})

const canSend = computed(() => !agentStore.sending && !agentStore.isSessionRunning)

function handleStop() {
  void agentStore.cancelCurrentSession(props.projectId)
}

// Batch generation detection
const batchStepCount = computed(() => {
  const stps = agentStore.currentSession?.steps || []
  let count = 0
  for (const step of stps) {
    const tool = String(step.tool || step.step_type || '')
    if (tool === 'generate_document_unit' || tool === 'write_document_unit') count++
  }
  return count
})

const totalChapters = computed(() => {
  // Extract target chapter count from user message or default to batchStepCount
  const msgs = messages.value
  let lastMsg = null
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i]?.role === 'user') {
      lastMsg = msgs[i]
      break
    }
  }
  const text = lastMsg?.content || ''
  const match = text.match(/(\d+)\s*[章篇]/)
  if (match) return Math.max(parseInt(match[1]!, 10), batchStepCount.value)
  return batchStepCount.value || 10
})

const hasBatchGeneration = computed(() => agentStore.isSessionRunning && batchStepCount.value > 0)

const selectedModelValue = computed({
  get: () => agentStore.selectedModel,
  set: (value: string) => agentStore.setSelectedModel(String(value || '')),
})

const modelOptions = computed(() => {
  if (!agentStore.models.length) {
    return [{
      value: '',
      label: agentStore.modelsLoading ? t('agent.center.loadingModels') : t('agent.center.defaultModel'),
      disabled: true,
    }]
  }
  return agentStore.models.map((model) => ({
    value: model.id,
    label: model.id,
  }))
})

function autoResizeInput() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

function scrollToBottom() {
  const el = timelineEl.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(
  () => [turnItems.value.length, agentStore.streamingText.length],
  () => {
    void nextTick(scrollToBottom)
  }
)

watch(draft, () => {
  void nextTick(autoResizeInput)
})

async function handleSend() {
  const message = draft.value.trim()
  if (!message || !canSend.value) return
  const skillSlug = effectiveSkillSlug.value
  draft.value = ''
  await nextTick()
  autoResizeInput()
  try {
    await agentStore.sendMessage(props.projectId, message, { skill_slug: skillSlug, effort: pickedEffort.value })
    pickedSkillSlug.value = null
    pickedEffort.value = null
  } catch {
    if (!draft.value) draft.value = message
  }
}

function detectMention() {
  const el = inputEl.value
  if (!el) {
    fileMentionVisible.value = false
    slashVisible.value = false
    return
  }
  const cursor = el.selectionStart ?? draft.value.length
  const before = draft.value.slice(0, cursor)
  const rect = el.getBoundingClientRect()
  // bottom = distance from popup bottom to viewport bottom = viewport height - rect.top + 4
  const bottomUp = window.innerHeight - rect.top + 4

  // / triggers slash command menu
  const slashMatch = before.match(/(^|\s)\/(\w*)$/)
  if (slashMatch) {
    const q = slashMatch[2] || ''
    slashQuery.value = q
    slashPos.value = { bottom: bottomUp, left: rect.left + 16 }
    // Determine mode from query
    if (q.startsWith('skill')) {
      slashMode.value = 'skill'
      slashQuery.value = q.slice(5)
    } else if (q.startsWith('model')) {
      slashMode.value = 'model'
      slashQuery.value = q.slice(5)
    } else if (q.startsWith('effort')) {
      slashMode.value = 'effort'
      slashQuery.value = q.slice(6)
    } else {
      slashMode.value = 'menu'
      slashQuery.value = q
    }
    slashVisible.value = true
    fileMentionVisible.value = false
    return
  }

  // @ triggers file picker (popup upward)
  const fileMatch = before.match(/(^|\s)@([\w./\-]*)$/)
  if (fileMatch) {
    fileMentionQuery.value = fileMatch[2] || ''
    fileMentionPos.value = { bottom: window.innerHeight - rect.top + 4, left: rect.left + 16 }
    fileMentionVisible.value = true
    slashVisible.value = false
    return
  }

  fileMentionVisible.value = false
  slashVisible.value = false
}

function pickSlashMenu(item: any) {
  slashMode.value = item.id
  slashQuery.value = ''
  // Clear the /xxx from input
  const el = inputEl.value
  const cursor = el?.selectionStart ?? draft.value.length
  const before = draft.value.slice(0, cursor)
  const after = draft.value.slice(cursor)
  draft.value = before.replace(/(^|\s)\/\w*$/, '$1') + `/${item.id}` + after
  slashPos.value = { bottom: slashPos.value.bottom, left: slashPos.value.left }
  void nextTick(() => inputEl.value?.focus())
}

function pickSlashSkill(skill: SkillItem) {
  const el = inputEl.value
  const cursor = el?.selectionStart ?? draft.value.length
  const before = draft.value.slice(0, cursor)
  const after = draft.value.slice(cursor)
  draft.value = before.replace(/(^|\s)\/?\w*skill\w*$/, '$1') + after
  pickedSkillSlug.value = skill.slug
  slashVisible.value = false
  slashMode.value = null
  void nextTick(() => inputEl.value?.focus())
}

function pickSlashModel(model: any) {
  const el = inputEl.value
  const cursor = el?.selectionStart ?? draft.value.length
  const before = draft.value.slice(0, cursor)
  const after = draft.value.slice(cursor)
  draft.value = before.replace(/(^|\s)\/?\w*model\w*$/, '$1') + after
  agentStore.setSelectedModel(model.id)
  slashVisible.value = false
  slashMode.value = null
  void nextTick(() => inputEl.value?.focus())
}

function pickSlashEffort(effort: any) {
  const el = inputEl.value
  const cursor = el?.selectionStart ?? draft.value.length
  const before = draft.value.slice(0, cursor)
  const after = draft.value.slice(cursor)
  draft.value = before.replace(/(^|\s)\/?\w*effort\w*$/, '$1') + after
  pickedEffort.value = effort.id
  slashVisible.value = false
  slashMode.value = null
  void nextTick(() => inputEl.value?.focus())
}

function pickFile(file: ProjectFile) {
  const el = inputEl.value
  const cursor = el?.selectionStart ?? draft.value.length
  const before = draft.value.slice(0, cursor)
  const after = draft.value.slice(cursor)
  draft.value = before.replace(/(^|\s)@[\w./\-]*$/, '$1') + `@[${file.path}]` + after
  fileMentionVisible.value = false
  void nextTick(() => inputEl.value?.focus())
}

function clearPickedSkill() {
  pickedSkillSlug.value = null
}

function handleInputKeydown(event: KeyboardEvent) {
  if (fileMentionVisible.value) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      filePopup.value?.moveDown()
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      filePopup.value?.moveUp()
      return
    }
    if ((event.key === 'Enter' || event.key === 'Tab') && !event.isComposing) {
      event.preventDefault()
      filePopup.value?.pickActive()
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      fileMentionVisible.value = false
          return
    }
  }
  if (slashVisible.value) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      slashPopup.value?.moveDown()
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      slashPopup.value?.moveUp()
      return
    }
    if ((event.key === 'Enter' || event.key === 'Tab') && !event.isComposing) {
      event.preventDefault()
      slashPopup.value?.pickActive()
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      slashVisible.value = false
      slashMode.value = null
      return
    }
    // Backspace at the / clears popup
    if (event.key === 'Backspace' && slashQuery.value === '' && slashMode.value === 'menu') {
      slashVisible.value = false
      slashMode.value = null
    }
  }
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void handleSend()
  }
}

function triggerFileUpload() {
  fileInputEl.value?.click()
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  attachedFiles.value.push(...files)
}

function removeAttachedFile(index: number) {
  attachedFiles.value.splice(index, 1)
}

// ----- Drag & drop support -----
const dragOver = ref(false)

function onDragEnter() {
  dragOver.value = true
}

function onDragLeave(e: DragEvent) {
  // Only hide if leaving the container itself, not a child
  if (e.currentTarget && !(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) {
    dragOver.value = false
  }
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) {
    attachedFiles.value.push(...files)
  }
  // Also handle dropped text
  const text = e.dataTransfer?.getData('text/plain')
  if (text && !files.length && !draft.value) {
    draft.value = text
  }
  e.preventDefault()
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}
</script>

<template>
  <section class="muse-workspace-panel muse-workspace-panel-chat min-w-0 flex-1">
    <div class="muse-workspace-bar">
      <p class="min-w-0 flex-1 truncate text-sm font-medium muse-text-body">
        {{ sessionTitle }}
      </p>
      <span
        v-if="sessionStatus"
        class="muse-workspace-status"
      >
        <Loader2
          v-if="agentStore.isSessionRunning"
          class="h-3 w-3 animate-spin muse-text-muted"
        />
        <span
          v-else
          class="h-1.5 w-1.5 rounded-full"
          :class="statusDotClass"
          aria-hidden="true"
        />
        <span class="text-[11px] muse-text-muted">{{ sessionStatusLabel }}</span>
      </span>
      <!-- Batch generation progress bar -->
      <div
        v-if="hasBatchGeneration"
        class="muse-progress-bar mt-1.5"
        style="grid-column: 1 / -1;"
      >
        <div
          class="muse-progress-bar-fill"
          :style="{ width: Math.min(100, (batchStepCount / totalChapters) * 100) + '%' }"
        />
      </div>
    </div>

    <div ref="timelineEl" class="muse-workspace-scroll">
      <!-- Empty state -->
      <div
        v-if="!agentStore.currentSessionId && !turnItems.length"
        class="muse-empty-state"
      >
        <Sparkles class="h-7 w-7 muse-text-accent" />
        <p class="text-sm font-medium muse-text-body">{{ t('agent.center.startTitle') }}</p>
        <p class="max-w-sm text-xs leading-relaxed muse-text-muted">
          {{ t('agent.center.startHint') }}
        </p>
      </div>

      <!-- Loading state -->
      <div v-else-if="agentStore.sessionLoading && !turnItems.length" class="flex justify-center py-8">
        <Loader2 class="h-5 w-5 animate-spin muse-text-faint" />
      </div>

      <!-- Turn-based conversation -->
      <div v-else class="flex w-full flex-col gap-3 px-1">
        <template v-for="(item, index) in turnItems" :key="`item-${index}`">
          <!-- Turn separator (between turns) -->
          <div
            v-if="index > 0 && item.kind === 'user' && turnItems[index - 1]?.turn !== item.turn"
            class="muse-turn-separator"
          >
            <span class="muse-turn-separator-line" />
            <span class="muse-turn-separator-label">Turn {{ item.turn }}</span>
            <span class="muse-turn-separator-line" />
          </div>

          <!-- Step card -->
          <RichMessageBubble
            v-if="item.kind === 'step'"
            :step="item.step"
          />

          <!-- User / Agent message -->
          <RichMessageBubble
            v-else-if="item.message"
            :message="item.message"
          />
        </template>

        <!-- Streaming bubble (no turn item yet) -->
        <RichMessageBubble
          v-if="agentStore.streamingThinkingText || (agentStore.isSessionRunning && !agentStore.streamingText)"
          :thinking-streaming="agentStore.isSessionRunning"
          :thinking-streaming-text="agentStore.streamingThinkingText"
        />
        <RichMessageBubble
          v-if="agentStore.streamingText"
          :streaming="true"
          :streaming-text="agentStore.streamingText"
        />
      </div>
    </div>

    <!-- Composer footer -->
    <div class="muse-workspace-footer">
      <div
        class="muse-workspace-composer"
        :class="{ 'muse-dragover': dragOver }"
        @dragenter.prevent="onDragEnter"
        @dragover.prevent="onDragOver"
        @dragleave="onDragLeave"
        @drop.prevent="onDrop"
      >
        <div v-if="attachedFiles.length" class="flex flex-wrap gap-1.5 px-3 pt-2">
          <span
            v-for="(file, index) in attachedFiles"
            :key="index"
            class="inline-flex items-center gap-1 rounded-md bg-[color:var(--muse-accent-soft)] px-2 py-0.5 text-[11px] font-medium text-[color:var(--muse-accent)]"
          >
            {{ file.name }}
            <button type="button" class="ml-0.5 hover:opacity-70" @click="removeAttachedFile(index)">
              <X class="h-3 w-3" />
            </button>
          </span>
        </div>
        <textarea
          ref="inputEl"
          v-model="draft"
          data-testid="agent-chat-input"
          rows="1"
          :placeholder="t('agent.center.inputPlaceholder')"
          class="muse-workspace-composer-input"
          @input="detectMention"
          @click="detectMention"
          @keydown="handleInputKeydown"
        />
        <div
          v-if="effectiveSkillSlug"
          class="muse-active-skill-chip mt-1 inline-flex items-center gap-1 rounded-md bg-[color:var(--muse-accent-soft)] px-2 py-0.5 text-[11px] font-medium text-[color:var(--muse-accent)]"
        >
          <Sparkles class="h-3 w-3" />
          skill: {{ effectiveSkillSlug }}
          <button
            v-if="pickedSkillSlug"
            type="button"
            class="ml-0.5 hover:opacity-70"
            :title="t('agent.center.clearSkill', '清除')"
            @click="clearPickedSkill"
          >
            <X class="h-3 w-3" />
          </button>
        </div>
        <div
          v-if="pickedEffort"
          class="muse-active-skill-chip mt-1 ml-1 inline-flex items-center gap-1 rounded-md bg-[color:var(--muse-accent-soft)] px-2 py-0.5 text-[11px] font-medium text-[color:var(--muse-accent)]"
        >
          effort: {{ pickedEffort }}
          <button
            type="button"
            class="ml-0.5 hover:opacity-70"
            title="清除"
            @click="pickedEffort = null"
          >
            <X class="h-3 w-3" />
          </button>
        </div>

        <FileMentionPopup
          ref="filePopup"
          :visible="fileMentionVisible"
          :query="fileMentionQuery"
          :items="projectFiles"
          :position="fileMentionPos"
          @select="pickFile"
          @dismiss="fileMentionVisible = false"
        />
        <!-- Slash command: root menu -->
        <SlashCommandPopup
          v-if="slashMode === 'menu'"
          ref="slashPopup"
          :visible="slashVisible"
          :query="slashQuery"
          :items="slashMenuItems"
          :position="slashPos"
          header-label="命令"
          empty-text="无匹配命令"
          @select="pickSlashMenu"
          @dismiss="slashVisible = false"
        >
          <template #item="{ item }">
            <span class="label">/{{ item.id }}</span>
            <span class="desc">{{ item.desc }}</span>
          </template>
        </SlashCommandPopup>
        <!-- Slash command: skill picker -->
        <SlashCommandPopup
          v-if="slashMode === 'skill'"
          ref="slashPopup"
          :visible="slashVisible"
          :query="slashQuery"
          :items="skills"
          :position="slashPos"
          header-label="Skill"
          empty-text="无匹配 skill"
          @select="pickSlashSkill"
          @dismiss="slashVisible = false"
        >
          <template #item="{ item }">
            <span class="label">{{ item.slug }}</span>
            <span class="desc">{{ item.name }}</span>
          </template>
        </SlashCommandPopup>
        <!-- Slash command: model picker -->
        <SlashCommandPopup
          v-if="slashMode === 'model'"
          ref="slashPopup"
          :visible="slashVisible"
          :query="slashQuery"
          :items="modelOptions.filter((m: any) => !m.disabled)"
          :position="slashPos"
          header-label="Model"
          empty-text="无可用模型"
          @select="pickSlashModel"
          @dismiss="slashVisible = false"
        >
          <template #item="{ item }">
            <span class="label">{{ item.value }}</span>
          </template>
        </SlashCommandPopup>
        <!-- Slash command: effort picker -->
        <SlashCommandPopup
          v-if="slashMode === 'effort'"
          ref="slashPopup"
          :visible="slashVisible"
          :query="slashQuery"
          :items="effortOptions"
          :position="slashPos"
          header-label="Effort"
          empty-text="无匹配"
          @select="pickSlashEffort"
          @dismiss="slashVisible = false"
        >
          <template #item="{ item }">
            <span class="label">{{ item.label }}</span>
            <span class="desc">{{ item.desc }}</span>
          </template>
        </SlashCommandPopup>
        <div class="muse-workspace-composer-bar">
          <input
            ref="fileInputEl"
            type="file"
            multiple
            class="hidden"
            @change="handleFileSelect"
          />
          <button
            type="button"
            class="muse-icon-btn !h-7 !w-7"
            :title="t('agent.center.attachFile')"
            @click="triggerFileUpload"
          >
            <Paperclip class="h-3.5 w-3.5" />
          </button>
          <div class="flex-1" />
          <DropdownSelect
            v-model="selectedModelValue"
            data-testid="agent-model-select"
            size="sm"
            class="muse-model-pill max-w-[160px]"
            :aria-label="t('common.model')"
            :disabled="agentStore.modelsLoading"
            :options="modelOptions"
            :placeholder="agentStore.modelsLoading ? t('agent.center.loadingModels') : t('agent.center.defaultModel')"
          />
          <button
            type="button"
            data-testid="agent-send-button"
            :aria-label="t('common.send')"
            :disabled="agentStore.isSessionRunning ? false : !canSend"
            class="muse-workspace-send-btn"
            :class="{ 'muse-workspace-send-btn-active': canSend || agentStore.isSessionRunning }"
            @click="agentStore.isSessionRunning ? handleStop() : handleSend()"
          >
            <Square v-if="agentStore.isSessionRunning" class="h-3.5 w-3.5" />
            <Loader2 v-else-if="agentStore.sending" class="h-3.5 w-3.5 animate-spin" />
            <SendHorizontal v-else class="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
