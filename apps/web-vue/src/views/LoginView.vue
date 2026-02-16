<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'

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
  <div class="flex min-h-screen items-center justify-center bg-slate-900 px-4">
    <div class="w-full max-w-sm">
      <div class="mb-8 text-center">
        <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600">
          <span class="text-xl font-bold text-white">M</span>
        </div>
        <h1 class="text-2xl font-bold text-white">Welcome back</h1>
        <p class="mt-1 text-sm text-slate-400">Sign in to your MuseGraph account</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleLogin">
        <Input
          v-model="email"
          label="Email"
          type="email"
          placeholder="you@example.com"
        />

        <Input
          v-model="password"
          label="Password"
          type="password"
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

      <p class="mt-6 text-center text-sm text-slate-400">
        Don't have an account?
        <router-link to="/register" class="text-blue-400 hover:text-blue-300 font-medium">
          Sign up
        </router-link>
      </p>
    </div>
  </div>
</template>
