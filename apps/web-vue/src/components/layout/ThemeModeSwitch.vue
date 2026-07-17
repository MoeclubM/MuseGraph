<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Monitor, Moon, Sun, Check } from '@lucide/vue'
import { useTheme, type ThemeMode } from '@/composables/useTheme'

const { themeMode, setTheme } = useTheme()

const open = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const dropdownPlacement = ref<'bottom' | 'top'>('bottom')

const options: Array<{ value: ThemeMode; label: string; icon: typeof Sun }> = [
  { value: 'system', label: 'System', icon: Monitor },
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
]

const currentIcon = computed(() => {
  const found = options.find((o) => o.value === themeMode.value)
  return found?.icon || Monitor
})

function toggle() {
  open.value = !open.value
  if (open.value) {
    void nextTick(updatePlacement)
  }
}

function updatePlacement() {
  if (!rootEl.value) return
  const rect = rootEl.value.getBoundingClientRect()
  const spaceBelow = window.innerHeight - rect.bottom
  dropdownPlacement.value = spaceBelow < 200 && rect.top > spaceBelow ? 'top' : 'bottom'
}

function selectOption(value: ThemeMode) {
  setTheme(value)
  open.value = false
}

function onDocumentClick(event: MouseEvent) {
  if (!rootEl.value?.contains(event.target as Node)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <div ref="rootEl" class="relative inline-flex">
    <button
      type="button"
      class="muse-icon-btn inline-flex h-8 w-8 items-center justify-center"
      :title="themeMode"
      :aria-label="themeMode"
      @click.stop="toggle"
    >
      <component :is="currentIcon" class="h-4 w-4" aria-hidden="true" />
    </button>

    <Transition
      enter-active-class="transition duration-100 ease-out"
      enter-from-class="opacity-0 -translate-y-0.5"
      leave-active-class="transition duration-75 ease-in"
      leave-to-class="opacity-0 -translate-y-0.5"
    >
      <div
        v-if="open"
        role="listbox"
        :class="[
          'absolute z-[60] min-w-[10rem] overflow-auto rounded-lg border border-[color:var(--muse-border)] bg-[color:var(--muse-panel)] py-1 shadow-lg',
          dropdownPlacement === 'bottom' ? 'top-full mt-1 origin-top' : 'bottom-full mb-1 origin-bottom right-0',
        ]"
        @click.stop
      >
        <button
          v-for="option in options"
          :key="option.value"
          type="button"
          role="option"
          :aria-selected="option.value === themeMode"
          :class="[
            'flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs transition-colors',
            option.value === themeMode
              ? 'bg-[color:var(--muse-accent-soft)] text-[color:var(--muse-accent)]'
              : 'text-[color:var(--muse-text)] hover:bg-[color:var(--muse-field-hover)]',
          ]"
          @click="selectOption(option.value)"
        >
          <Check
            v-if="option.value === themeMode"
            class="h-3.5 w-3.5 shrink-0"
            aria-hidden="true"
          />
          <span v-else class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <component :is="option.icon" class="h-3.5 w-3.5 shrink-0" />
          <span class="min-w-0 flex-1 whitespace-nowrap">{{ option.label }}</span>
        </button>
      </div>
    </Transition>
  </div>
</template>
