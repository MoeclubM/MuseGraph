<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import ThemeModeSwitch from '@/components/layout/ThemeModeSwitch.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const email = ref('')
const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!email.value || !password.value) {
    toast.warning('Please fill in all fields')
    return
  }
  loading.value = true
  try {
    await authStore.login(email.value, password.value)
    toast.success('Welcome back!')
    const redirect = (route.query.redirect as string) || '/dashboard'
    router.push(redirect)
  } catch {
    // API interceptor handles the error toast
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="relative flex min-h-screen items-center justify-center bg-[#f7f3e8] px-4 dark:bg-zinc-950">
    <div class="absolute right-4 top-4">
      <ThemeModeSwitch />
    </div>
    <div class="muse-surface w-full max-w-sm rounded-md p-5 sm:p-6 dark:border-zinc-800 dark:bg-zinc-900/90">
      <div class="mb-8 text-center">
        <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-md bg-amber-600">
          <span class="text-xl font-bold text-white">M</span>
        </div>
        <h1 class="text-2xl font-bold text-stone-900 dark:text-stone-100">Welcome back</h1>
        <p class="mt-1 text-sm text-stone-500 dark:text-stone-400">Sign in to your MuseGraph account</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleLogin">
        <Input
          v-model="email"
          label="Email"
          name="email"
          type="email"
          autocomplete="username"
          autocapitalize="off"
          :spellcheck="false"
          placeholder="you@example.com"
        />

        <Input
          v-model="password"
          label="Password"
          name="password"
          type="password"
          autocomplete="current-password"
          placeholder="Enter your password"
        />

        <Button
          type="submit"
          variant="primary"
          size="lg"
          :loading="loading"
          class="w-full"
        >
          Sign In
        </Button>
      </form>

      <p class="mt-6 text-center text-sm text-stone-500 dark:text-stone-400">
        Don't have an account?
        <router-link to="/register" class="font-medium text-amber-700 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-300">
          Sign up
        </router-link>
      </p>
      <p class="mt-3 text-center text-xs text-stone-500 dark:text-stone-400">
        Admin?
        <router-link to="/admin/login" class="font-medium text-amber-700 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-300">
          Sign in here
        </router-link>
      </p>
    </div>
  </div>
</template>
