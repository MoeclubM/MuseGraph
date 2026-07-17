<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import LocaleSwitch from '@/components/layout/LocaleSwitch.vue'
import MuseLogo from '@/components/layout/MuseLogo.vue'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const authStore = useAuthStore()
const toast = useToast()

const email = ref('')
const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!email.value || !password.value) {
    toast.warning(t('validation.fillAllFields'))
    return
  }
  loading.value = true
  try {
    await authStore.login(email.value, password.value)
    toast.success(t('toast.welcomeBack'))
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
  <div class="muse-auth-page">
    <div class="absolute right-4 top-4 flex items-center gap-2">
      <LocaleSwitch />
    </div>
    <div class="muse-card muse-auth-card">
      <div class="mb-8 text-center">
        <MuseLogo size="md" />
        <h1 class="mt-4 text-2xl muse-text-title">{{ t('auth.login.title') }}</h1>
        <p class="mt-1 muse-text-caption">{{ t('auth.login.subtitle') }}</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleLogin">
        <Input
          v-model="email"
          :label="t('auth.login.emailLabel')"
          name="email"
          type="email"
          autocomplete="username"
          autocapitalize="off"
          :spellcheck="false"
          :placeholder="t('auth.login.emailPlaceholder')"
        />

        <Input
          v-model="password"
          :label="t('auth.login.passwordLabel')"
          name="password"
          type="password"
          autocomplete="current-password"
          :placeholder="t('auth.login.passwordPlaceholder')"
        />

        <Button
          type="submit"
          variant="primary"
          size="lg"
          :loading="loading"
          class="w-full"
        >
          {{ t('auth.login.submit') }}
        </Button>
      </form>

      <p class="mt-6 text-center text-sm muse-text-muted">
        {{ t('auth.login.noAccount') }}
        <router-link to="/register" class="font-medium muse-text-accent hover:opacity-80">
          {{ t('auth.login.signUpLink') }}
        </router-link>
      </p>
    </div>
  </div>
</template>
