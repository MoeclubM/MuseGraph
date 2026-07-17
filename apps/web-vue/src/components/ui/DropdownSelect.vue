<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useAttrs, watch } from 'vue'
import { Check, ChevronDown } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { dropdownSelectSizeClasses, type ControlSize } from '@/lib/control-sizes'

defineOptions({
  inheritAttrs: false,
})

export interface DropdownSelectOption {
  value: string
  label: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue?: string
    options?: DropdownSelectOption[]
    disabled?: boolean
    placeholder?: string
    ariaLabel?: string
    size?: ControlSize
  }>(),
  {
    modelValue: '',
    options: () => [],
    disabled: false,
    placeholder: '',
    ariaLabel: '',
    size: 'md',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const attrs = useAttrs()
const open = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const triggerEl = ref<HTMLButtonElement | null>(null)
const panelWidthPx = ref(0)
const activeIndex = ref(-1)
const dropdownPlacement = ref<'bottom' | 'top'>('bottom')

const selectedOption = computed(() =>
  props.options.find((option) => option.value === props.modelValue),
)

const displayLabel = computed(
  () => selectedOption.value?.label || props.placeholder || props.modelValue || '',
)

function updatePlacement() {
  if (!rootEl.value) return
  const rect = rootEl.value.getBoundingClientRect()
  const spaceBelow = window.innerHeight - rect.bottom
  dropdownPlacement.value = spaceBelow < 200 && rect.top > spaceBelow ? 'top' : 'bottom'
}

function close() {
  open.value = false
}

function syncPanelWidth() {
  const triggerWidth = triggerEl.value?.offsetWidth ?? 0
  const longestLabel = props.options.reduce((max, option) => {
    return Math.max(max, option.label.length)
  }, 0)
  const estimatedWidth = Math.max(triggerWidth, Math.min(320, longestLabel * 8 + 56))
  panelWidthPx.value = Math.max(triggerWidth, estimatedWidth, 128)
}

function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    const index = props.options.findIndex((option) => option.value === props.modelValue)
    activeIndex.value = index >= 0 ? index : 0
    void nextTick(() => {
      syncPanelWidth()
      updatePlacement()
    })
  }
}

function selectOption(option: DropdownSelectOption) {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  close()
}

function onDocumentClick(event: MouseEvent) {
  if (!rootEl.value?.contains(event.target as Node)) {
    close()
  }
}

function onKeydown(event: KeyboardEvent) {
  if (!open.value) {
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
      event.preventDefault()
      toggle()
    }
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, props.options.length - 1)
    return
  }

  if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
    return
  }

  if (event.key === 'Enter' && activeIndex.value >= 0) {
    event.preventDefault()
    const option = props.options[activeIndex.value]
    if (option) selectOption(option)
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})

watch(open, (isOpen) => {
  if (isOpen) {
    void nextTick(() => {
      syncPanelWidth()
      updatePlacement()
    })
  }
})
</script>

<template>
  <div
    ref="rootEl"
    class="relative inline-block w-full"
    :class="attrs.class as string | undefined"
  >
    <button
      ref="triggerEl"
      type="button"
      role="combobox"
      :data-testid="attrs['data-testid'] as string | undefined"
      :aria-expanded="open"
      :aria-haspopup="true"
      :aria-label="ariaLabel || undefined"
      :disabled="disabled"
      :class="cn(
        'muse-field-base muse-focus-ring flex w-full items-center justify-between gap-1.5 rounded-md text-left outline-none',
        dropdownSelectSizeClasses[size],
        disabled && 'cursor-not-allowed opacity-60',
        open && 'border-[color:var(--muse-accent)]',
      )"
      @click.stop="toggle"
      @keydown="onKeydown"
    >
      <span class="min-w-0 flex-1 truncate whitespace-nowrap">{{ displayLabel }}</span>
      <ChevronDown
        :class="cn(
          'h-3.5 w-3.5 shrink-0 text-[color:var(--muse-text-muted)] transition-transform duration-150',
          open && 'rotate-180 text-[color:var(--muse-accent)]',
        )"
        aria-hidden="true"
      />
    </button>

    <Transition
      enter-active-class="transition duration-100 ease-out"
      enter-from-class="opacity-0 -translate-y-0.5"
      leave-active-class="transition duration-75 ease-in"
      leave-to-class="opacity-0 -translate-y-0.5"
    >
      <div
        v-if="open && options.length"
        role="listbox"
        :style="{ minWidth: panelWidthPx ? `${panelWidthPx}px` : undefined }"
        :class="cn(
          'absolute z-[60] max-h-56 w-max min-w-full overflow-auto rounded-lg border border-[color:var(--muse-border)] bg-[color:var(--muse-panel)] py-1 shadow-lg',
          dropdownPlacement === 'bottom' ? 'top-full mt-1 origin-top' : 'bottom-full mb-1 origin-bottom',
        )"
        @click.stop
      >
        <button
          v-for="(option, index) in options"
          :key="option.value || `option-${index}`"
          type="button"
          role="option"
          :aria-selected="option.value === modelValue"
          :disabled="option.disabled"
          :class="cn(
            'flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs transition-colors',
            option.value === modelValue
              ? 'bg-[color:var(--muse-accent-soft)] text-[color:var(--muse-accent)]'
              : 'text-[color:var(--muse-text)] hover:bg-[color:var(--muse-field-hover)]',
            index === activeIndex && option.value !== modelValue && 'bg-[color:var(--muse-field-hover)]',
            option.disabled && 'cursor-not-allowed opacity-50',
          )"
          @mouseenter="activeIndex = index"
          @click="selectOption(option)"
        >
          <Check
            v-if="option.value === modelValue"
            class="h-3.5 w-3.5 shrink-0"
            aria-hidden="true"
          />
          <span v-else class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span class="min-w-0 flex-1 whitespace-nowrap">{{ option.label }}</span>
        </button>
      </div>
    </Transition>
  </div>
</template>
