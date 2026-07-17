<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import { selectSizeClasses, type ControlSize } from '@/lib/control-sizes'

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(
  defineProps<{
    modelValue?: unknown
    disabled?: boolean
    error?: string
    size?: ControlSize
    ariaLabel?: string
  }>(),
  {
    modelValue: undefined,
    disabled: false,
    error: '',
    size: 'md',
    ariaLabel: '',
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const attrs = useAttrs()

const selectVariants = cva(
  'muse-field-base muse-focus-ring w-full cursor-pointer appearance-none rounded-md outline-none',
  {
    variants: {
      size: {
        sm: selectSizeClasses.sm,
        md: selectSizeClasses.md,
        lg: selectSizeClasses.lg,
      },
      state: {
        default: '',
        error: 'muse-field-error',
      },
    },
    defaultVariants: {
      size: 'md',
      state: 'default',
    },
  }
)

const classes = computed(() =>
  cn(
    selectVariants({
      size: props.size,
      state: props.error ? 'error' : 'default',
    }),
    attrs.class as string | undefined
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
  <div class="group relative inline-block w-full">
    <select
      v-bind="{ ...attrs, class: undefined }"
      :value="modelValue"
      :disabled="disabled"
      :aria-label="ariaLabel || undefined"
      :class="classes"
      @change="onChange"
    >
      <slot />
    </select>
    <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-[color:var(--muse-text-muted)] transition-colors duration-150 group-hover:text-[color:var(--muse-text)] group-focus-within:text-[color:var(--muse-accent)]">
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
