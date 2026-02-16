<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'

const router = useRouter()
const authStore = useAuthStore()
const toast = useToast()

const email = ref('')
const username = ref('')
const password = ref('')
const nickname = ref('')
const loading = ref(false)

async function handleRegister() {
  if (!email.value || !username.value || !password.value) {
    toast.warning('Please fill in all required fields')
    return
  }
  if (password.value.length < 6) {
    toast.warning('Password must be at least 6 characters')
    return
  }
  loading.value = true
  try {
    await authStore.register(email.value, username.value, password.value, nickname.value || undefined)
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
  <div class="flex min-h-screen items-center justify-center bg-slate-900 px-4">
    <div class="w-full max-w-sm">
      <div class="mb-8 text-center">
        <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600">
          <span class="text-xl font-bold text-white">M</span>
        </div>
        <h1 class="text-2xl font-bold text-white">Create an account</h1>
        <p class="mt-1 text-sm text-slate-400">Get started with MuseGraph</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleRegister">
        <Input
          v-model="email"
          label="Email"
          type="email"
          placeholder="you@example.com"
        />

        <Input
          v-model="username"
          label="Username"
          type="text"
          placeholder="Choose a username"
        />

        <Input
          v-model="nickname"
          label="Nickname (optional)"
          type="text"
          placeholder="Display name"
        />

        <Input
          v-model="password"
          label="Password"
          type="password"
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

      <p class="mt-6 text-center text-sm text-slate-400">
        Already have an account?
        <router-link to="/login" class="text-blue-400 hover:text-blue-300 font-medium">
          Sign in
        </router-link>
      </p>
    </div>
  </div>
</template>
