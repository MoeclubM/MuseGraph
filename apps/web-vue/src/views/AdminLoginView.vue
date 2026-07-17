<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import MuseLogo from '@/components/layout/MuseLogo.vue'
import LocaleSwitch from '@/components/layout/LocaleSwitch.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const toast = useToast()

const email = ref('')
const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!email.value.trim() || !password.value.trim()) {
    toast.warning(t('validation.adminCredentialsRequired'))
    return
  }

  loading.value = true
  try {
    await authStore.login(email.value.trim(), password.value)
    if (!authStore.isAdmin) {
      await authStore.logout()
      toast.error(t('toast.noAdminAccess'))
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
  <div class="muse-auth-page">
    <div class="absolute right-4 top-4 flex items-center gap-2">
      <LocaleSwitch />
    </div>
    <div class="muse-card muse-auth-card">
      <div class="mb-6 text-center">
        <MuseLogo size="md" />
        <h1 class="mt-3 text-xl font-semibold muse-text-title">{{ t('auth.adminLogin.title') }}</h1>
        <p class="mt-1 muse-text-caption">{{ t('auth.adminLogin.subtitle') }}</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleLogin">
        <Input
          v-model="email"
          :label="t('auth.adminLogin.emailLabel')"
          name="email"
          type="email"
          autocomplete="username"
          autocapitalize="off"
          :spellcheck="false"
          :placeholder="t('auth.adminLogin.emailPlaceholder')"
        />
        <Input
          v-model="password"
          :label="t('auth.adminLogin.passwordLabel')"
          name="password"
          type="password"
          autocomplete="current-password"
          :placeholder="t('auth.adminLogin.passwordPlaceholder')"
        />

        <Button type="submit" variant="primary" class="w-full" :loading="loading">
          {{ t('auth.adminLogin.submit') }}
        </Button>
      </form>

      <Button
        variant="ghost"
        size="sm"
        class="mt-4 h-auto w-full py-1 text-xs muse-text-muted hover:muse-text-body"
        @click="router.push('/login')"
      >
        {{ t('auth.adminLogin.switchToUser') }}
      </Button>
    </div>
  </div>
</template>
