<script setup lang="ts">
import { Search } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { controlSizeClasses, type ControlSize } from '@/lib/control-sizes'

withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    ariaLabel?: string
    size?: ControlSize
    inputClass?: string
    testId?: string
  }>(),
  {
    modelValue: '',
    size: 'sm',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  search: []
}>()

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="muse-panel-search min-w-0 flex-1">
    <div class="muse-panel-search-field">
      <Search class="muse-panel-search-icon" aria-hidden="true" />
      <input
        type="search"
        :value="modelValue"
        class="muse-panel-search-input muse-focus-ring outline-none"
        :class="cn(controlSizeClasses[size], 'pl-8', inputClass)"
        :placeholder="placeholder"
        :aria-label="ariaLabel || placeholder"
        :data-testid="testId"
        @input="onInput"
        @keydown.enter.prevent="emit('search')"
      />
    </div>
  </div>
</template>