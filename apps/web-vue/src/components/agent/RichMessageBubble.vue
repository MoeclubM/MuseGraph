<script setup lang="ts">
import { computed, ref } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useTypewriter } from '@/composables/useTypewriter'
import type { AgentMessage, AgentStep } from '@/types'

const props = defineProps<{
  message?: AgentMessage
  step?: AgentStep
  streaming?: boolean
  streamingText?: string
  thinkingStreaming?: boolean
  thinkingStreamingText?: string
}>()

const expanded = ref(false)

const isUser = computed(() => props.message?.role === 'user')
const isThinkingStep = computed(() => String(props.step?.step_type || '') === 'thinking')

const isToolStep = computed(() => {
  if (!props.step || isThinkingStep.value) return false
  const t = String(props.step.step_type || '')
  return t && !['finalize', 'retry', 'plan', 'context_snapshot'].includes(t)
})

const rawContent = computed(() => {
  if (props.streaming && props.streamingText != null) return props.streamingText
  if (props.step) {
    const preview = String(props.step.tool_result_preview || '').trim()
    const output = String(props.step.output || '').trim()
    if (isToolStep.value) {
      if (preview) return preview
      if (output.length > 400) return output.slice(0, 400) + '…'
      return output
    }
    if (preview) return preview
    if (output) return output
    return ''
  }
  return props.message?.content || ''
})

const { displayed: streamDisplayed } = useTypewriter(() => (props.streaming ? props.streamingText || '' : ''), {
  enabled: () => !!props.streaming,
})

const thinkingSource = computed(() => props.thinkingStreamingText || (isThinkingStep.value ? rawContent.value : ''))
const { displayed: thinkingDisplayed } = useTypewriter(() => thinkingSource.value, {
  enabled: () => !!(props.thinkingStreaming || (isThinkingStep.value && String(props.step?.status || '').toLowerCase() === 'running')),
})

const content = computed(() => {
  if (props.streaming) return streamDisplayed.value
  return rawContent.value
})

const title = computed(() => {
  if (props.step) {
    if (isThinkingStep.value) return props.step.message || '思考过程'
    const msg = String(props.step.message || '').trim()
    if (msg) return msg
    return props.step.title || props.step.step_type || props.step.tool || ''
  }
  return ''
})

const statusIcon = computed(() => {
  if (!props.step) return ''
  const s = String(props.step.status || '').toLowerCase()
  if (s === 'running' || s === 'pending') return '⟳'
  if (s === 'completed') return '✓'
  if (s === 'failed') return '✗'
  return ''
})

const statusColor = computed(() => {
  if (!props.step) return ''
  const s = String(props.step.status || '').toLowerCase()
  if (s === 'running' || s === 'pending') return 'text-amber-500'
  if (s === 'completed') return 'text-emerald-500'
  if (s === 'failed') return 'text-red-500'
  return 'muse-text-faint'
})

const canToggle = computed(() => {
  if (!props.step) return false
  if (isThinkingStep.value) return !!(props.step.output || thinkingSource.value)
  const out = String(props.step.output || '').trim()
  const prev = String(props.step.tool_result_preview || '').trim()
  if (!out && !prev) return false
  if (out && prev && out === prev) return out.length > 120
  return !!(out || prev)
})

const showThinkingPanel = computed(() => !!(props.thinkingStreaming || props.thinkingStreamingText))

function wordCount(text: string): number {
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/g) || []).length
  const other = text.replace(/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/g, ' ').split(/\s+/).filter(Boolean).length
  return cjk + other
}

const wordCountBadge = computed(() => {
  if (!props.step) return ''
  const tool = String(props.step.tool || props.step.step_type || '')
  if ((tool === 'generate_document_unit' || tool === 'write_document_unit') && content.value) {
    const wc = wordCount(content.value)
    if (wc > 0) return `${wc} 字`
  }
  return ''
})

function toggleExpanded() {
  if (!canToggle.value) return
  expanded.value = !expanded.value
}
</script>

<template>
  <div v-if="showThinkingPanel" class="muse-thinking-panel muse-message-enter">
    <div class="muse-thinking-header">
      <span class="muse-thinking-label">思考过程</span>
      <span v-if="thinkingStreaming" class="muse-chat-cursor muse-thinking-cursor" />
    </div>
    <pre class="muse-thinking-body">{{ thinkingDisplayed }}</pre>
  </div>

  <div v-if="message && isUser" class="flex justify-end muse-message-enter">
    <div class="muse-chat-bubble muse-chat-bubble-user max-w-[80%] rounded-xl rounded-tr-sm px-4 py-2.5">
      <MarkdownRenderer v-if="content" :text="content" />
      <span v-else class="muse-text-faint italic">{{ message.content }}</span>
    </div>
  </div>

  <div v-else-if="message && !isUser" class="flex justify-start muse-message-enter">
    <div class="muse-chat-bubble muse-chat-bubble-agent max-w-[88%]">
      <MarkdownRenderer :text="content" />
    </div>
  </div>

  <div v-else-if="streaming && streamingText" class="flex justify-start muse-message-enter">
    <div class="muse-chat-bubble muse-chat-bubble-agent max-w-[88%]">
      <MarkdownRenderer :text="streamDisplayed" />
      <span class="muse-chat-cursor" />
    </div>
  </div>

  <div
    v-else-if="step && step.step_type !== 'context_snapshot'"
    class="muse-step-card muse-message-enter"
    :class="{ 'muse-step-card-collapsed': canToggle && !expanded }"
  >
    <div
      class="muse-step-card-header"
      :class="{ 'cursor-pointer': canToggle || isThinkingStep }"
      @click="canToggle ? toggleExpanded() : (isThinkingStep ? (expanded = !expanded) : undefined)"
    >
      <span v-if="canToggle || isThinkingStep" class="muse-step-chevron shrink-0" :class="{ 'muse-step-chevron-open': expanded }">›</span>
      <span v-if="title" class="muse-step-card-title">{{ title }}</span>
      <span v-if="wordCountBadge" class="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">{{ wordCountBadge }}</span>
      <span v-if="statusIcon" class="muse-step-card-status" :class="statusColor">{{ statusIcon }}</span>
      <span v-if="step.model" class="muse-step-card-model">{{ step.model }}</span>
    </div>
    <div v-if="content && expanded && !isThinkingStep" class="muse-step-card-body">
      <MarkdownRenderer :text="content" />
    </div>
    <div v-else-if="isThinkingStep && expanded" class="muse-step-card-body muse-thinking-body-inline">
      <pre>{{ content }}</pre>
    </div>
  </div>
</template>
