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
  'muse-field-base muse-focus-ring w-full min-h-28 rounded-md px-3.5 py-3 text-sm outline-none',
  {
    variants: {
      state: {
        default: '',
        error: 'muse-field-error',
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
