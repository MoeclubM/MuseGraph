<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import ThemeModeSwitch from '@/components/layout/ThemeModeSwitch.vue'

const router = useRouter()
const authStore = useAuthStore()
const toast = useToast()

const email = ref('')
const password = ref('')
const nickname = ref('')
const loading = ref(false)

async function handleRegister() {
  if (!email.value || !nickname.value || !password.value) {
    toast.warning('Please fill in all required fields')
    return
  }
  if (password.value.length < 6) {
    toast.warning('Password must be at least 6 characters')
    return
  }
  loading.value = true
  try {
    await authStore.register(email.value, password.value, nickname.value)
    toast.success('Account created successfully!')
    router.push('/dashboard')
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
        <h1 class="text-2xl font-bold text-stone-900 dark:text-stone-100">Create an account</h1>
        <p class="mt-1 text-sm text-stone-500 dark:text-stone-400">Get started with MuseGraph</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleRegister">
        <Input
          v-model="email"
          label="Email"
          name="email"
          type="email"
          autocomplete="email"
          autocapitalize="off"
          :spellcheck="false"
          placeholder="you@example.com"
        />

        <Input
          v-model="nickname"
          label="Nickname"
          name="nickname"
          type="text"
          autocomplete="nickname"
          placeholder="Display name"
        />

        <Input
          v-model="password"
          label="Password"
          name="password"
          type="password"
          autocomplete="new-password"
          placeholder="At least 6 characters"
        />

        <Button
          type="submit"
          variant="primary"
          size="lg"
          :loading="loading"
          class="w-full"
        >
          Create Account
        </Button>
      </form>

      <p class="mt-6 text-center text-sm text-stone-500 dark:text-stone-400">
        Already have an account?
        <router-link to="/login" class="font-medium text-amber-700 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-300">
          Sign in
        </router-link>
      </p>
    </div>
  </div>
</template>
