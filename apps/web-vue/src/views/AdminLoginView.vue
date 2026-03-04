<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import { Shield } from 'lucide-vue-next'
import ThemeModeSwitch from '@/components/layout/ThemeModeSwitch.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const toast = useToast()

const email = ref('')
const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!email.value.trim() || !password.value.trim()) {
    toast.warning('请输入管理员账号和密码')
    return
  }

  loading.value = true
  try {
    await authStore.login(email.value.trim(), password.value)
    if (!authStore.isAdmin) {
      await authStore.logout()
      toast.error('当前账号无管理员权限')
      return
    }
    const redirect = (route.query.redirect as string) || '/admin'
    router.push(redirect)
  } catch {
    // API interceptor handles toast
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
    <div class="w-full max-w-sm rounded-2xl border border-stone-300 bg-[#fbf7ef] p-5 shadow-lg sm:p-6 dark:border-zinc-800 dark:bg-zinc-900/80 dark:shadow-2xl">
      <div class="mb-6 text-center">
        <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-amber-600">
          <Shield class="h-6 w-6 text-white" />
        </div>
        <h1 class="text-xl font-semibold text-stone-900 dark:text-stone-100">管理员登录</h1>
        <p class="mt-1 text-sm text-stone-500 dark:text-stone-400">仅管理员账号可访问后台控制台</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleLogin">
        <Input v-model="email" label="管理员邮箱" type="email" placeholder="admin@example.com" />
        <Input v-model="password" label="密码" type="password" placeholder="输入密码" />

        <Button type="submit" variant="primary" class="w-full" :loading="loading">
          登录后台
        </Button>
      </form>

      <Button
        variant="ghost"
        size="sm"
        class="mt-4 h-auto w-full py-1 text-xs text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
        @click="router.push('/login')"
      >
        切换到普通用户登录
      </Button>
    </div>
  </div>
</template>
