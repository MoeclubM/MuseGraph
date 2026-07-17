<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    readonly?: boolean
    compact?: boolean
  }>(),
  {
    placeholder: 'Start writing...',
    readonly: false,
    compact: false,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()
const textarea = ref<HTMLTextAreaElement | null>(null)

function autoResize() {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.max(el.scrollHeight, props.compact ? 120 : 200) + 'px'
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
  <div class="relative flex h-full flex-col">
    <textarea
      ref="textarea"
      :value="modelValue"
      :placeholder="placeholder"
      :readonly="readonly"
      :class="[
        'muse-textarea w-full flex-1 resize-none leading-relaxed transition-colors focus:outline-none',
        compact ? 'min-h-[120px] px-3 py-2 text-xs' : 'min-h-[200px] rounded-lg border px-4 py-3 text-sm',
        !compact && 'border-[color:var(--muse-border)] bg-[color:var(--muse-field)] text-[color:var(--muse-text)] placeholder:text-[color:var(--muse-text-faint)] focus:border-[color:var(--muse-accent)] focus:ring-1 focus:ring-[color:var(--muse-ring)]',
        compact && 'border-0 bg-transparent text-[color:var(--muse-text)] placeholder:text-[color:var(--muse-text-faint)]',
      ]"
      @input="onInput"
    />
    <div v-if="!compact" class="flex items-center justify-end px-1 py-1.5">
      <span class="text-xs muse-text-faint">
        {{ t('agent.editor.charCount', { count: modelValue.length.toLocaleString() }) }}
      </span>
    </div>
  </div>
</template>
