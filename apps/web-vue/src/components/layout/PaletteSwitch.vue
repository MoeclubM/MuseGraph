<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Palette, Check } from '@lucide/vue'
import { useTheme } from '@/composables/useTheme'
import { palettes, paletteLabels, type PaletteId } from '@/composables/palettes'

const { paletteId, setPalette } = useTheme()

const open = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const dropdownPlacement = ref<'bottom' | 'top'>('bottom')

const options = computed(() =>
  (Object.keys(palettes) as PaletteId[]).map((id) => ({
    id,
    label: paletteLabels[id],
    swatch: palettes[id].swatch,
  })),
)

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

function selectOption(id: PaletteId) {
  setPalette(id)
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
      :title="$t('nav.palette')"
      :aria-label="$t('nav.palette')"
      @click.stop="toggle"
    >
      <Palette class="h-4 w-4" aria-hidden="true" />
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
          :key="option.id"
          type="button"
          role="option"
          :aria-selected="option.id === paletteId"
          :class="[
            'flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs transition-colors',
            option.id === paletteId
              ? 'bg-[color:var(--muse-accent-soft)] text-[color:var(--muse-accent)]'
              : 'text-[color:var(--muse-text)] hover:bg-[color:var(--muse-field-hover)]',
          ]"
          @click="selectOption(option.id)"
        >
          <Check
            v-if="option.id === paletteId"
            class="h-3.5 w-3.5 shrink-0"
            aria-hidden="true"
          />
          <span v-else class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span
            class="h-3.5 w-3.5 shrink-0 rounded-full border border-[color:var(--muse-border)]"
            :style="{ backgroundColor: option.swatch }"
          />
          <span class="min-w-0 flex-1 whitespace-nowrap">{{ option.label }}</span>
        </button>
      </div>
    </Transition>
  </div>
</template>
