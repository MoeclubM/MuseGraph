<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{
  text: string
}>()

marked.setOptions({
  breaks: true,
  gfm: true,
})

const rendered = computed(() => {
  if (!props.text) return ''
  return DOMPurify.sanitize(marked.parse(props.text, { breaks: true, gfm: true }) as string)
})
</script>

<template>
  <div class="muse-markdown" v-html="rendered" />
</template>
