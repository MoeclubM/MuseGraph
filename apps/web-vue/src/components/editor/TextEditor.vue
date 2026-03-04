<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    readonly?: boolean
  }>(),
  {
    placeholder: 'Start writing...',
    readonly: false,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const textarea = ref<HTMLTextAreaElement | null>(null)

function autoResize() {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.max(el.scrollHeight, 200) + 'px'
}

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
  autoResize()
}

watch(
  () => props.modelValue,
  () => nextTick(autoResize)
)

onMounted(() => {
  nextTick(autoResize)
})
</script>

<template>
  <div class="relative flex flex-col h-full">
    <textarea
      ref="textarea"
      :value="modelValue"
      :placeholder="placeholder"
      :readonly="readonly"
      class="w-full flex-1 resize-none rounded-lg border border-stone-300 bg-stone-50 px-4 py-3 text-sm text-stone-800 placeholder-stone-400 leading-relaxed focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 transition-colors dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-100 dark:placeholder-zinc-500"
      @input="onInput"
    />
    <div class="flex items-center justify-end px-1 py-1.5">
      <span class="text-xs text-stone-500 dark:text-zinc-500">
        {{ modelValue.length.toLocaleString() }} characters
      </span>
    </div>
  </div>
</template>

