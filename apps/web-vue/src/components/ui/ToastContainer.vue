<script setup lang="ts">
import Toast from './Toast.vue'
import { useToast } from '@/composables/useToast'

const { toasts, removeToast } = useToast()
</script>

<template>
  <div class="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
    <TransitionGroup
      enter-active-class="transition-all duration-300"
      leave-active-class="transition-all duration-300"
      enter-from-class="opacity-0 translate-x-8"
      leave-to-class="opacity-0 translate-x-8"
    >
      <div v-for="toast in toasts" :key="toast.id" class="pointer-events-auto">
        <Toast
          :message="toast.message"
          :type="toast.type"
          @close="removeToast(toast.id)"
        />
      </div>
    </TransitionGroup>
  </div>
</template>
