<script setup lang="ts">
import { computed } from 'vue'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    modelValue?: unknown
    disabled?: boolean
    error?: string
  }>(),
  {
    modelValue: undefined,
    disabled: false,
    error: '',
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const selectVariants = cva(
  'muse-field-base muse-focus-ring h-11 w-full appearance-none rounded-md px-3.5 pr-12 text-sm outline-none',
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
    selectVariants({
      state: props.error ? 'error' : 'default',
    })
  )
)

function onChange(e: Event) {
  const target = e.target as HTMLSelectElement
  const option = target.selectedOptions?.[0] as (HTMLOptionElement & { _value?: unknown }) | undefined
  const next = option && Object.prototype.hasOwnProperty.call(option, '_value')
    ? option._value
    : target.value
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="group relative">
    <select
      :value="modelValue"
      :disabled="disabled"
      :class="classes"
      @change="onChange"
    >
      <slot />
    </select>
    <div class="pointer-events-none absolute inset-y-0 right-0 flex w-11 items-center justify-center text-[color:var(--muse-text-muted)] transition-colors duration-150 group-hover:text-[color:var(--muse-text)]">
      <span class="absolute inset-y-2 left-0 w-px bg-[color:var(--muse-field-divider)]"></span>
      <svg
        class="h-4 w-4"
        viewBox="0 0 20 20"
        fill="none"
        aria-hidden="true"
      >
        <path d="M6 8L10 12L14 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </div>
  </div>
</template>

<style scoped>
:deep(option),
:deep(optgroup) {
  background: var(--muse-panel);
  color: var(--muse-text);
}
</style>
