<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Provider } from '@/types'
import Card from '@/components/ui/Card.vue'
import Modal from '@/components/ui/Modal.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Select from '@/components/ui/Select.vue'
import AdminFormField from '@/components/admin/AdminFormField.vue'

const props = defineProps<{
  providers: Provider[]
  showProviderForm: boolean
  providerForm: {
    id: string
    name: string
    provider: string
    api_key: string
    base_url: string
    is_active: boolean
    priority: number
  }
  providerTypeOptions: { value: string; label: string }[]
}>()

const emit = defineEmits<{
  'new-provider': []
  'edit-provider': [provider: Provider]
  'close-provider-form': []
  'save-provider': []
  'remove-provider': [id: string]
}>()

const { t } = useI18n()

const searchQuery = ref('')
const statusFilter = ref<'' | 'active' | 'inactive'>('')

const filteredProviders = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return props.providers.filter((provider) => {
    if (query) {
      const haystack = `${provider.name} ${provider.provider} ${provider.base_url || ''}`.toLowerCase()
      if (!haystack.includes(query)) return false
    }
    if (statusFilter.value === 'active' && !provider.is_active) return false
    if (statusFilter.value === 'inactive' && provider.is_active) return false
    return true
  })
})

function providerTypeLabel(value: string): string {
  const match = props.providerTypeOptions.find((item) => item.value === value)
  return match?.label || value
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-2">
      <div>
        <h2 class="text-sm font-semibold muse-text-heading">{{ t('admin.providers.title') }}</h2>
        <p class="text-xs muse-text-muted">
          {{ t('admin.providers.filters.resultCount', { shown: filteredProviders.length, total: providers.length }) }}
        </p>
      </div>
      <Button size="sm" @click="emit('new-provider')">{{ t('admin.providers.newProvider') }}</Button>
    </div>

    <Card variant="inset" class="muse-card-compact">
      <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_10rem]">
        <AdminFormField :label="t('admin.providers.filters.searchLabel')">
          <Input
            v-model="searchQuery"
            size="sm"
            :placeholder="t('admin.providers.filters.searchName')"
          />
        </AdminFormField>
        <AdminFormField :label="t('admin.providers.filters.statusLabel')">
          <Select v-model="statusFilter" size="sm" :aria-label="t('admin.providers.filters.statusLabel')">
            <option value="">{{ t('admin.providers.filters.allStatus') }}</option>
            <option value="active">{{ t('admin.providers.filters.statusActive') }}</option>
            <option value="inactive">{{ t('admin.providers.filters.statusInactive') }}</option>
          </Select>
        </AdminFormField>
      </div>
    </Card>

    <Modal
      :show="showProviderForm"
      size="lg"
      :title="t('admin.providers.settings')"
      @close="emit('close-provider-form')"
    >
      <div class="space-y-4">
        <p class="text-xs muse-text-muted">{{ t('admin.providers.settingsSubtitle') }}</p>

      <div class="space-y-3">
        <p class="text-xs font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.providers.sectionIdentity') }}</p>
        <div class="grid gap-3 md:grid-cols-2">
          <AdminFormField
            :label="t('admin.providers.fields.name')"
            :description="t('admin.providers.fields.nameHint')"
          >
            <Input
              v-model="providerForm.name"
              size="sm"
              :placeholder="t('admin.providers.fields.namePlaceholder')"
            />
          </AdminFormField>
          <AdminFormField
            :label="t('admin.providers.fields.type')"
            :description="t('admin.providers.fields.typeHint')"
          >
            <Select
              v-model="providerForm.provider"
              size="sm"
              :aria-label="t('admin.providers.fields.type')"
            >
              <option value="" disabled>{{ t('admin.providers.selectType') }}</option>
              <option v-for="item in providerTypeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
            </Select>
          </AdminFormField>
        </div>
      </div>

      <div class="space-y-3">
        <p class="text-xs font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.providers.sectionConnection') }}</p>
        <div class="grid gap-3 md:grid-cols-2">
          <AdminFormField
            :label="t('admin.providers.fields.apiKey')"
            :description="t('admin.providers.fields.apiKeyHint')"
          >
            <Input
              v-model="providerForm.api_key"
              type="password"
              autocomplete="off"
              size="sm"
              :placeholder="t('admin.providers.fields.apiKeyPlaceholder')"
            />
          </AdminFormField>
          <AdminFormField
            :label="t('admin.providers.fields.baseUrl')"
            :description="t('admin.providers.fields.baseUrlHint')"
          >
            <Input
              v-model="providerForm.base_url"
              size="sm"
              :placeholder="t('admin.providers.fields.baseUrlPlaceholder')"
            />
          </AdminFormField>
        </div>
      </div>

      <div class="space-y-3">
        <p class="text-xs font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.providers.sectionRouting') }}</p>
        <div class="grid gap-3 md:grid-cols-2">
          <AdminFormField
            :label="t('admin.providers.fields.priority')"
            :description="t('admin.providers.fields.priorityHint')"
          >
            <Input
              v-model.number="providerForm.priority"
              type="number"
              size="sm"
              :placeholder="t('admin.providers.fields.priorityPlaceholder')"
            />
          </AdminFormField>
          <label class="flex items-start justify-between gap-3 rounded-md border border-[color:var(--muse-border)] bg-[color:var(--muse-field)] px-3 py-2.5">
            <div class="min-w-0">
              <p class="text-sm font-medium muse-text-body">{{ t('admin.providers.fields.isActive') }}</p>
              <p class="mt-0.5 text-xs muse-text-muted">{{ t('admin.providers.fields.isActiveHint') }}</p>
            </div>
            <Checkbox v-model="providerForm.is_active" class="mt-0.5 shrink-0" />
          </label>
        </div>
      </div>

      <div class="flex justify-end gap-2 border-t border-[color:var(--muse-border)] pt-3">
        <Button size="sm" variant="secondary" @click="emit('close-provider-form')">{{ t('common.cancel') }}</Button>
        <Button size="sm" @click="emit('save-provider')">{{ t('common.save') }}</Button>
      </div>
      </div>
    </Modal>

    <Card variant="compact" :stack="false">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-[color:var(--muse-bg-soft)]">
            <tr class="border-b border-[color:var(--muse-border)]">
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.providers.columns.name') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.providers.columns.type') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.providers.columns.baseUrl') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.providers.columns.status') }}</th>
              <th class="px-2 py-1.5 text-right text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.common.action') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in filteredProviders"
              :key="p.id"
              class="border-b border-[color:var(--muse-border)] transition-colors hover:bg-[color:var(--muse-field-hover)]"
            >
              <td class="px-2 py-1.5 text-xs font-medium muse-text-body">{{ p.name }}</td>
              <td class="px-2 py-1.5 text-xs muse-text-muted">{{ providerTypeLabel(p.provider) }}</td>
              <td class="max-w-[240px] truncate px-2 py-1.5 text-xs muse-text-muted">{{ p.base_url || '—' }}</td>
              <td class="px-2 py-1.5">
                <span
                  class="muse-badge"
                  :class="p.is_active
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                    : 'border-stone-300/80 bg-stone-100 text-stone-600 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400'"
                >
                  {{ p.is_active ? t('admin.providers.statusActive') : t('admin.providers.statusInactive') }}
                </span>
              </td>
              <td class="px-2 py-1.5 text-right">
                <div class="flex flex-wrap justify-end gap-1.5">
                  <Button size="sm" variant="secondary" @click="emit('edit-provider', p)">{{ t('admin.common.edit') }}</Button>
                  <Button size="sm" variant="danger" @click="emit('remove-provider', p.id)">{{ t('admin.common.delete') }}</Button>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredProviders.length">
              <td colspan="5" class="px-2 py-6 text-center text-xs muse-text-muted">{{ t('admin.providers.filters.noResults') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>