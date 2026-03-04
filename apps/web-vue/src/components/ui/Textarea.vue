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
  'w-full min-h-20 rounded-md border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 shadow-xs outline-none transition-[color,box-shadow] placeholder:text-stone-400 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:placeholder:text-zinc-500',
  {
    variants: {
      state: {
        default: 'focus-visible:border-amber-500 focus-visible:ring-[3px] focus-visible:ring-amber-500/35',
        error: 'border-red-500 focus-visible:border-red-500 focus-visible:ring-[3px] focus-visible:ring-red-500/30',
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
