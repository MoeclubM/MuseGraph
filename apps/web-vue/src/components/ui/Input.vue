<script setup lang="ts">
import { computed } from 'vue'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

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
    inputClass?: string
    modelModifiers?: Record<string, boolean>
  }>(),
  {
    type: 'text',
    disabled: false,
    modelValue: '',
    modelModifiers: () => ({}),
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const inputVariants = cva(
  'h-9 w-full rounded-xl border border-stone-300/90 bg-stone-100/92 px-3 text-sm text-stone-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] outline-none transition-all duration-200 placeholder:text-stone-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800/88 dark:text-zinc-100 dark:placeholder:text-zinc-500',
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

const inputClasses = computed(() =>
  cn(
    inputVariants({
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
    <label v-if="label" class="block text-sm font-medium text-stone-700 dark:text-stone-300">
      {{ label }}
    </label>
    <input
      :type="type"
      :placeholder="placeholder"
      :value="modelValue"
      :disabled="disabled"
      :min="min"
      :max="max"
      :step="step"
      :list="list"
      :autocomplete="autocomplete"
      :class="inputClasses"
      @input="onInput"
    />
    <p v-if="error" class="text-xs text-red-600 dark:text-red-300">{{ error }}</p>
  </div>
</template>
