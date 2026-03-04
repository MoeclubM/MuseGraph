<script setup lang="ts">
defineProps<{
  show: boolean
  title?: string
}>()

const emit = defineEmits<{
  close: []
}>()

function onBackdrop(e: MouseEvent) {
  if (e.target === e.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-200"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div
        v-if="show"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        @mousedown="onBackdrop"
      >
        <div class="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-lg border border-stone-300/90 bg-stone-50 shadow-lg dark:border-zinc-700/70 dark:bg-zinc-900">
          <div v-if="title" class="flex items-center justify-between border-b border-stone-300 px-6 py-4 dark:border-zinc-700">
            <h2 class="text-lg font-semibold text-stone-900 dark:text-stone-100">{{ title }}</h2>
            <button
              class="rounded-md p-1 text-stone-500 transition-colors hover:bg-stone-200 hover:text-stone-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              @click="emit('close')"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="p-6">
            <slot />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
