<script setup lang="ts">
import { computed } from 'vue'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    rows?: number
    placeholder?: string
    disabled?: boolean
    error?: string
  }>(),
  {
    modelValue: '',
    rows: 4,
    placeholder: '',
    disabled: false,
    error: '',
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const textareaVariants = cva(
  'w-full min-h-20 rounded-xl border border-stone-300/90 bg-stone-100/92 px-3 py-2 text-sm text-stone-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] outline-none transition-all duration-200 placeholder:text-stone-400 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800/88 dark:text-zinc-200 dark:placeholder:text-zinc-500',
  {
    variants: {
      state: {
        default: 'focus-visible:border-amber-500 focus-visible:ring-[3px] focus-visible:ring-amber-500/35',
        error: 'border-red-500/90 focus-visible:border-red-500 focus-visible:ring-[3px] focus-visible:ring-red-500/30',
      },
    },
    defaultVariants: {
      state: 'default',
    },
  }
)

const classes = computed(() =>
  cn(
    textareaVariants({
      state: props.error ? 'error' : 'default',
    })
  )
)

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}
</script>

<template>
  <textarea
    :rows="rows"
    :placeholder="placeholder"
    :value="modelValue"
    :disabled="disabled"
    :class="classes"
    @input="onInput"
  ></textarea>
</template>
