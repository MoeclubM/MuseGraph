<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import LocaleSwitch from '@/components/layout/LocaleSwitch.vue'
import MuseLogo from '@/components/layout/MuseLogo.vue'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const toast = useToast()

const email = ref('')
const password = ref('')
const nickname = ref('')
const loading = ref(false)

async function handleRegister() {
  if (!email.value || !nickname.value || !password.value) {
    toast.warning(t('validation.fillRequiredFields'))
    return
  }
  if (password.value.length < 6) {
    toast.warning(t('validation.passwordMinLength'))
    return
  }
  loading.value = true
  try {
    await authStore.register(email.value, password.value, nickname.value)
    toast.success(t('toast.accountCreated'))
    router.push('/dashboard')
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
        <h1 class="mt-4 text-2xl muse-text-title">{{ t('auth.register.title') }}</h1>
        <p class="mt-1 muse-text-caption">{{ t('auth.register.subtitle') }}</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleRegister">
        <Input
          v-model="email"
          :label="t('auth.register.emailLabel')"
          name="email"
          type="email"
          autocomplete="email"
          autocapitalize="off"
          :spellcheck="false"
          :placeholder="t('auth.register.emailPlaceholder')"
        />

        <Input
          v-model="nickname"
          :label="t('auth.register.nicknameLabel')"
          name="nickname"
          type="text"
          autocomplete="nickname"
          :placeholder="t('auth.register.nicknamePlaceholder')"
        />

        <Input
          v-model="password"
          :label="t('auth.register.passwordLabel')"
          name="password"
          type="password"
          autocomplete="new-password"
          :placeholder="t('auth.register.passwordPlaceholder')"
        />

        <Button
          type="submit"
          variant="primary"
          size="lg"
          :loading="loading"
          class="w-full"
        >
          {{ t('auth.register.submit') }}
        </Button>
      </form>

      <p class="mt-6 text-center text-sm muse-text-muted">
        {{ t('auth.register.hasAccount') }}
        <router-link to="/login" class="font-medium muse-text-accent hover:opacity-80">
          {{ t('auth.register.signInLink') }}
        </router-link>
      </p>
    </div>
  </div>
</template>
