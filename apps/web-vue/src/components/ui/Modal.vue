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
        <div class="bg-slate-800 rounded-xl shadow-2xl border border-slate-700 w-full max-w-lg max-h-[90vh] overflow-y-auto">
          <div v-if="title" class="flex items-center justify-between px-6 py-4 border-b border-slate-700">
            <h2 class="text-lg font-semibold text-slate-100">{{ title }}</h2>
            <button
              class="text-slate-400 hover:text-slate-200 transition-colors"
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
