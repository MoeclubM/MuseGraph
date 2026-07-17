<script setup lang="ts">
import { computed, useId } from 'vue'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import { controlSizeClasses, type ControlSize } from '@/lib/control-sizes'

const props = withDefaults(
  defineProps<{
    label?: string
    type?: string
    placeholder?: string
    error?: string
    modelValue?: string | number
    disabled?: boolean
    min?: string | number
    max?: string | number
    step?: string | number
    list?: string
    autocomplete?: string
    id?: string
    name?: string
    autocapitalize?: string
    spellcheck?: boolean
    size?: ControlSize
    inputClass?: string
    modelModifiers?: Record<string, boolean>
  }>(),
  {
    type: 'text',
    disabled: false,
    modelValue: '',
    spellcheck: false,
    size: 'md',
    modelModifiers: () => ({}),
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const generatedId = useId()

const inputId = computed(() => String(props.id || props.name || generatedId))

const inputVariants = cva('muse-field-base muse-focus-ring w-full rounded-md outline-none', {
  variants: {
    size: {
      sm: controlSizeClasses.sm,
      md: controlSizeClasses.md,
      lg: controlSizeClasses.lg,
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
})

const inputClasses = computed(() =>
  cn(
    inputVariants({
      size: props.size,
      state: props.error ? 'error' : 'default',
    }),
    props.inputClass
  )
)

function onInput(e: Event) {
  const target = e.target as HTMLInputElement
  const raw = target.value
  const useNumber = props.modelModifiers?.number || props.type === 'number'
  if (!useNumber) {
    emit('update:modelValue', raw)
    return
  }
  if (raw === '') {
    emit('update:modelValue', '')
    return
  }
  const next = Number(raw)
  emit('update:modelValue', Number.isNaN(next) ? raw : next)
}
</script>

<template>
  <div class="space-y-1.5">
    <label v-if="label" :for="inputId" class="block text-sm font-medium text-[color:var(--muse-text-muted)]">
      {{ label }}
    </label>
    <input
      :id="inputId"
      :name="name"
      :type="type"
      :placeholder="placeholder"
      :value="modelValue"
      :disabled="disabled"
      :min="min"
      :max="max"
      :step="step"
      :list="list"
      :autocomplete="autocomplete"
      :autocapitalize="autocapitalize"
      :spellcheck="spellcheck"
      :class="inputClasses"
      @input="onInput"
    />
    <p v-if="error" class="text-xs text-[color:var(--muse-danger)]">{{ error }}</p>
  </div>
</template>
