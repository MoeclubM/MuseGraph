<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label?: string
    type?: string
    placeholder?: string
    error?: string
    modelValue?: string
    disabled?: boolean
  }>(),
  {
    type: 'text',
    disabled: false,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const inputClasses = computed(() => {
  const base =
    'w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed'
  const borderClass = props.error
    ? 'border-red-500 focus:ring-red-500'
    : 'border-slate-700 focus:border-blue-500 focus:ring-blue-500'
  return [base, borderClass].join(' ')
})

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="space-y-1.5">
    <label v-if="label" class="block text-sm font-medium text-slate-300">
      {{ label }}
    </label>
    <input
      :type="type"
      :placeholder="placeholder"
      :value="modelValue"
      :disabled="disabled"
      :class="inputClasses"
      @input="onInput"
    />
    <p v-if="error" class="text-xs text-red-400">{{ error }}</p>
  </div>
</template>
