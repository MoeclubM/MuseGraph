<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{
  text: string
}>()

marked.setOptions({
  breaks: true,
  gfm: true,
})

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

const rendered = computed(() => {
  if (!props.text) return ''
  try {
    return marked.parse(props.text, { breaks: true, gfm: true }) as string
  } catch {
    return escapeHtml(props.text)
  }
})
</script>

<template>
  <div class="muse-markdown" v-html="rendered" />
</template>