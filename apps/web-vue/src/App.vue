<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import ToastContainer from './components/ui/ToastContainer.vue'

const authStore = useAuthStore()

onMounted(() => {
  authStore.init()
})
</script>

<template>
  <div class="min-h-screen bg-[#f7f3e8] text-stone-900 dark:bg-zinc-900 dark:text-zinc-100">
    <router-view />
    <ToastContainer />
  </div>
</template>
