<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    modelValue?: boolean
    disabled?: boolean
    class?: string
  }>(),
  {
    modelValue: false,
    disabled: false,
    class: '',
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const classes = computed(() =>
  cn(
    'h-4 w-4 shrink-0 rounded border-stone-300 bg-stone-100 text-amber-600 accent-amber-600 outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800',
    props.class
  )
)

function onChange(e: Event) {
  emit('update:modelValue', (e.target as HTMLInputElement).checked)
}
</script>

<template>
  <input
    type="checkbox"
    :checked="!!modelValue"
    :disabled="disabled"
    :class="classes"
    @change="onChange"
  />
</template>

