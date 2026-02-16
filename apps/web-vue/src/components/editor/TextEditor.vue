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
      class="w-full flex-1 resize-none rounded-lg border border-slate-700 bg-slate-800/50 px-4 py-3 text-sm text-slate-100 placeholder-slate-500 leading-relaxed focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
      @input="onInput"
    />
    <div class="flex items-center justify-end px-1 py-1.5">
      <span class="text-xs text-slate-500">
        {{ modelValue.length.toLocaleString() }} characters
      </span>
    </div>
  </div>
</template>
