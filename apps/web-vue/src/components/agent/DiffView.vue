<script setup lang="ts">
/**
 * Simple unified diff viewer.
 * Accepts a unified-diff string or before/after text and renders
 * a side-by-side or inline view of additions/removals.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(defineProps<{
  /** Unified diff string (---/+++ header + @@ lines) */
  diff?: string
  /** Optional before/after strings for simple comparison */
  original?: string
  modified?: string
  maxHeight?: number
}>(), {
  maxHeight: 260,
})

const { t } = useI18n()

type DiffLine = {
  type: 'add' | 'del' | 'ctx' | 'hunk'
  text: string
  oldLine?: number
  newLine?: number
}

function parseUnifiedDiff(diff: string): DiffLine[] {
  const lines = diff.split('\n')
  const result: DiffLine[] = []
  for (const line of lines) {
    if (line.startsWith('+++') || line.startsWith('---')) {
      continue // skip header
    }
    if (line.startsWith('@@')) {
      result.push({ type: 'hunk', text: line })
      continue
    }
    if (line.startsWith('+')) {
      result.push({ type: 'add', text: line })
      continue
    }
    if (line.startsWith('-')) {
      result.push({ type: 'del', text: line })
      continue
    }
    result.push({ type: 'ctx', text: line })
  }
  return result
}

const diffLines = computed<DiffLine[]>(() => {
  if (props.diff) return parseUnifiedDiff(props.diff)
  if (props.original != null && props.modified != null) {
    // Simple word-by-word or line-by-line comparison
    const origLines = props.original.split('\n')
    const modLines = props.modified.split('\n')
    const maxLen = Math.max(origLines.length, modLines.length)
    const lines: DiffLine[] = []
    for (let i = 0; i < maxLen; i++) {
      const o = origLines[i] ?? ''
      const m = modLines[i] ?? ''
      if (o !== m) {
        if (o) lines.push({ type: 'del', text: `- ${o}` })
        if (m) lines.push({ type: 'add', text: `+ ${m}` })
      } else {
        lines.push({ type: 'ctx', text: ` ${o}` })
      }
    }
    return lines
  }
  return []
})

const expanded = ref(false)
const toggle = () => { expanded.value = !expanded.value }
</script>

<template>
  <div
    v-if="diffLines.length"
    class="muse-diff-view"
    :style="!expanded ? { maxHeight: `${maxHeight}px` } : undefined"
  >
    <div class="muse-diff-scroll">
      <div
        v-for="(line, i) in diffLines"
        :key="i"
        class="muse-diff-line"
        :class="{
          'muse-diff-add': line.type === 'add',
          'muse-diff-del': line.type === 'del',
          'muse-diff-hunk': line.type === 'hunk',
        }"
      >
        <span class="muse-diff-prefix">{{ line.text.charAt(0) }}</span>
        <span class="muse-diff-text">{{ line.text.slice(1) }}</span>
      </div>
    </div>
    <button
      v-if="diffLines.length > 15"
      class="muse-diff-toggle"
      @click="toggle"
    >
      {{ expanded ? t('agent.diff.showLess') : t('agent.diff.showAll', { n: diffLines.length }) }}
    </button>
  </div>
  <div v-else-if="!diff" class="muse-diff-empty">
    {{ t('agent.diff.noChanges') }}
  </div>
</template>