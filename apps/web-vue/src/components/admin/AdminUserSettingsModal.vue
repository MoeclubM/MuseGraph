<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AdminUser } from '@/types'
import Modal from '@/components/ui/Modal.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import AdminFormField from '@/components/admin/AdminFormField.vue'
import { resetUserPassword, updateUser } from '@/api/admin'

const props = defineProps<{
  show: boolean
  user: AdminUser | null
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const { t } = useI18n()

const saving = ref(false)
const error = ref('')
const isAdmin = ref(false)
const status = ref<'ACTIVE' | 'SUSPENDED' | 'DELETED'>('ACTIVE')
const balance = ref(0)
const newPassword = ref('')
const confirmPassword = ref('')

const title = computed(() => {
  if (!props.user) return t('admin.users.settings.title')
  const label = props.user.nickname || props.user.email
  return t('admin.users.settings.titleFor', { name: label })
})

watch(
  () => [props.show, props.user] as const,
  ([open, user]) => {
    if (!open || !user) return
    error.value = ''
    saving.value = false
    isAdmin.value = Boolean(user.is_admin)
    status.value = user.status
    balance.value = Number(user.balance || 0)
    newPassword.value = ''
    confirmPassword.value = ''
  },
  { immediate: true },
)

async function save() {
  if (!props.user) return
  error.value = ''
  const password = newPassword.value.trim()
  const confirm = confirmPassword.value.trim()
  if (password || confirm) {
    if (password.length < 6) {
      error.value = t('validation.passwordMinLength')
      return
    }
    if (password !== confirm) {
      error.value = t('admin.users.settings.passwordMismatch')
      return
    }
  }

  saving.value = true
  try {
    await updateUser(props.user.id, {
      is_admin: isAdmin.value,
      status: status.value,
      balance: Number(balance.value),
    })
    if (password) {
      await resetUserPassword(props.user.id, password)
    }
    emit('saved')
    emit('close')
  } catch (e: unknown) {
    const maybe = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = maybe.response?.data?.detail || maybe.message || t('admin.users.settings.saveFailed')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal :show="show && !!user" :title="title" @close="emit('close')">
    <div v-if="user" class="space-y-5">
      <p class="text-sm muse-text-muted">
        {{ user.email }}
      </p>

      <Alert v-if="error" variant="destructive">{{ error }}</Alert>

      <AdminFormField
        :label="t('admin.users.settings.permissionLabel')"
        :description="t('admin.users.settings.permissionHint')"
      >
        <Select v-model="isAdmin" size="lg" :disabled="saving">
          <option :value="false">{{ t('admin.users.normalUser') }}</option>
          <option :value="true">{{ t('admin.users.administrator') }}</option>
        </Select>
      </AdminFormField>

      <AdminFormField
        :label="t('common.status')"
        :description="t('admin.users.settings.statusHint')"
      >
        <Select v-model="status" size="lg" :disabled="saving">
          <option value="ACTIVE">ACTIVE</option>
          <option value="SUSPENDED">SUSPENDED</option>
          <option value="DELETED">DELETED</option>
        </Select>
      </AdminFormField>

      <AdminFormField
        :label="t('admin.users.balance')"
        :description="t('admin.users.settings.balanceHint')"
      >
        <Input
          v-model.number="balance"
          type="number"
          min="0"
          step="0.01"
          :disabled="saving"
        />
      </AdminFormField>

      <div class="space-y-3 border-t border-stone-300/80 pt-4 dark:border-zinc-700/60">
        <p class="text-sm font-medium muse-text-body">{{ t('admin.users.settings.passwordSection') }}</p>
        <AdminFormField
          :label="t('admin.users.settings.newPassword')"
          :description="t('admin.users.settings.passwordHint')"
        >
          <Input
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            :placeholder="t('admin.users.settings.passwordPlaceholder')"
            :disabled="saving"
          />
        </AdminFormField>
        <AdminFormField :label="t('admin.users.settings.confirmPassword')">
          <Input
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            :disabled="saving"
          />
        </AdminFormField>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <Button variant="secondary" :disabled="saving" @click="emit('close')">
          {{ t('common.cancel') }}
        </Button>
        <Button variant="primary" :disabled="saving" @click="save">
          {{ saving ? t('admin.users.settings.saving') : t('common.save') }}
        </Button>
      </div>
    </div>
  </Modal>
</template>