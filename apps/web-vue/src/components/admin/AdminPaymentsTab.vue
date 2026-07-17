<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { EpayAdapterConfig, PaymentAdapterAdmin, PaymentAdapterTypeMeta } from '@/types'
import Card from '@/components/ui/Card.vue'
import Modal from '@/components/ui/Modal.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Select from '@/components/ui/Select.vue'
import AdminFormField from '@/components/admin/AdminFormField.vue'

const props = defineProps<{
  adapters: PaymentAdapterAdmin[]
  adapterTypes: PaymentAdapterTypeMeta[]
  loading?: boolean
}>()

const emit = defineEmits<{
  create: [payload: { adapter_type: string; display_name: string }]
  save: [adapterId: string, payload: Record<string, unknown>]
  'toggle-enabled': [adapterId: string, enabled: boolean]
  delete: [adapterId: string]
}>()

const { t } = useI18n()

// New adapter creation
const showCreateForm = ref(false)
const newAdapterType = ref('epay')
const newDisplayName = ref('')

// Edit adapter modal
const showEditModal = ref(false)
const editingAdapter = ref<PaymentAdapterAdmin | null>(null)
const editKeyInput = ref('')
const editPaymentTypes = ref<string[]>([])

const channelOptions = ['alipay', 'wxpay', 'qqpay'] as const

const typeLabel = computed(() => {
  const map = new Map(props.adapterTypes.map((item) => [item.id, item.label]))
  return (id: string) => map.get(id) || id
})

function epayConfig(adapter: PaymentAdapterAdmin): EpayAdapterConfig {
  return adapter.config || {
    url: '', pid: '', key: '', has_key: false,
    payment_types: ['alipay'], notify_url: '', return_url: '',
  }
}

function openCreateModal() {
  newAdapterType.value = 'epay'
  newDisplayName.value = ''
  showCreateForm.value = true
}

function submitCreate() {
  const name = newDisplayName.value.trim()
  if (!name) return
  emit('create', { adapter_type: newAdapterType.value, display_name: name })
  showCreateForm.value = false
}

function openEditModal(adapter: PaymentAdapterAdmin) {
  editingAdapter.value = { ...adapter, config: { ...adapter.config } }
  const cfg = epayConfig(adapter)
  editKeyInput.value = ''
  editPaymentTypes.value = [...(cfg.payment_types || ['alipay'])]
  showEditModal.value = true
}

function toggleEditPaymentType(channel: string, checked: boolean) {
  const set = new Set(editPaymentTypes.value)
  if (checked) set.add(channel)
  else set.delete(channel)
  editPaymentTypes.value = channelOptions.filter((c) => set.has(c))
  if (!editPaymentTypes.value.length) editPaymentTypes.value = ['alipay']
}

function submitEdit() {
  const adapter = editingAdapter.value
  if (!adapter) return
  const cfg = epayConfig(adapter)
  emit('save', adapter.id, {
    display_name: adapter.display_name,
    enabled: adapter.enabled,
    sort_order: adapter.sort_order,
    config: {
      url: cfg.url,
      pid: cfg.pid,
      key: editKeyInput.value || '',
      payment_types: editPaymentTypes.value.length ? editPaymentTypes.value : ['alipay'],
      notify_url: cfg.notify_url,
      return_url: cfg.return_url,
    },
  })
  showEditModal.value = false
  editingAdapter.value = null
}

function confirmDelete(adapterId: string) {
  if (confirm(t('admin.payments.deleteConfirm') || '确定删除？')) {
    emit('delete', adapterId)
  }
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-2">
      <div>
        <h2 class="text-sm font-semibold muse-text-heading">{{ t('admin.payments.title') }}</h2>
        <p class="text-xs muse-text-muted">
          {{ t('admin.payments.subtitle') }}
        </p>
      </div>
      <Button size="sm" @click="openCreateModal">{{ t('admin.payments.addAdapter') }}</Button>
    </div>

    <!-- Create adapter modal -->
    <Modal
      :show="showCreateForm"
      size="md"
      :title="t('admin.payments.addAdapter')"
      @close="showCreateForm = false"
    >
      <div class="space-y-4">
        <AdminFormField :label="t('admin.payments.type')">
          <Select v-model="newAdapterType" size="md">
            <option v-for="type in adapterTypes" :key="type.id" :value="type.id">{{ type.label }}</option>
          </Select>
        </AdminFormField>
        <AdminFormField :label="t('admin.payments.displayName')">
          <Input v-model="newDisplayName" :placeholder="t('admin.payments.displayName')" />
        </AdminFormField>
        <div class="flex justify-end gap-2 border-t border-[color:var(--muse-border)] pt-3">
          <Button size="sm" variant="secondary" @click="showCreateForm = false">{{ t('common.cancel') }}</Button>
          <Button size="sm" @click="submitCreate">{{ t('admin.payments.add') }}</Button>
        </div>
      </div>
    </Modal>

    <!-- Edit adapter modal -->
    <Modal
      :show="showEditModal"
      size="lg"
      :title="editingAdapter?.display_name || t('admin.payments.editAdapter')"
      @close="showEditModal = false"
    >
      <div v-if="editingAdapter" class="space-y-4">
        <div class="grid gap-3 md:grid-cols-2">
          <AdminFormField :label="t('admin.payments.displayName')">
            <Input v-model="editingAdapter.display_name" size="sm" />
          </AdminFormField>
          <AdminFormField :label="t('admin.payments.sortOrder')">
            <Input v-model.number="editingAdapter.sort_order" type="number" size="sm" />
          </AdminFormField>
        </div>

        <p class="text-xs font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.payments.sectionGateway') }}</p>
        <div class="grid gap-3 md:grid-cols-2">
          <AdminFormField :label="t('admin.payments.gatewayUrl')">
            <Input v-model="editingAdapter.config.url" size="sm" :placeholder="t('admin.payments.gatewayUrl')" />
          </AdminFormField>
          <AdminFormField :label="t('admin.payments.merchantPid')">
            <Input v-model="editingAdapter.config.pid" size="sm" :placeholder="t('admin.payments.merchantPid')" />
          </AdminFormField>
          <AdminFormField :label="t('admin.payments.commKey')">
            <Input
              v-model="editKeyInput"
              type="password"
              size="sm"
              :placeholder="editingAdapter.config.has_key ? t('admin.payments.keyKeep') : t('admin.payments.commKey')"
            />
          </AdminFormField>
          <AdminFormField :label="t('admin.payments.notifyUrl')">
            <Input v-model="editingAdapter.config.notify_url" size="sm" :placeholder="t('admin.payments.notifyUrl')" />
          </AdminFormField>
        </div>
        <AdminFormField :label="t('admin.payments.returnUrl')">
          <Input v-model="editingAdapter.config.return_url" size="sm" :placeholder="t('admin.payments.returnUrl')" />
        </AdminFormField>

        <p class="text-xs font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.payments.sectionTypes') }}</p>
        <div class="flex flex-wrap gap-3">
          <label
            v-for="channel in channelOptions"
            :key="channel"
            class="inline-flex items-center gap-2 text-sm muse-text-body"
          >
            <Checkbox
              :model-value="editPaymentTypes.includes(channel)"
              @update:model-value="toggleEditPaymentType(channel, Boolean($event))"
            />
            {{ t(`admin.payments.types.${channel}`) }}
          </label>
        </div>

        <div class="flex justify-end gap-2 border-t border-[color:var(--muse-border)] pt-3">
          <Button size="sm" variant="secondary" @click="showEditModal = false">{{ t('common.cancel') }}</Button>
          <Button size="sm" @click="submitEdit">{{ t('common.save') }}</Button>
        </div>
      </div>
    </Modal>

    <!-- Adapters table -->
    <Card variant="compact" :stack="false">
      <div v-if="!adapters.length" class="px-2 py-6 text-center text-xs muse-text-muted">
        {{ t('admin.payments.empty') }}
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-[color:var(--muse-bg-soft)]">
            <tr class="border-b border-[color:var(--muse-border)]">
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.payments.columns.name') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.payments.columns.type') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.payments.columns.status') }}</th>
              <th class="px-2 py-1.5 text-right text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.common.action') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="adapter in adapters"
              :key="adapter.id"
              class="border-b border-[color:var(--muse-border)] transition-colors hover:bg-[color:var(--muse-field-hover)]"
            >
              <td class="px-2 py-1.5 text-xs font-medium muse-text-body">
                <span class="flex items-center gap-1.5">
                  {{ adapter.display_name }}
                  <span v-if="!adapter.valid" class="text-[10px] text-amber-600 dark:text-amber-400"> · {{ t('admin.payments.incomplete') }}</span>
                </span>
              </td>
              <td class="px-2 py-1.5 text-xs muse-text-muted">{{ typeLabel(adapter.adapter_type) }}</td>
              <td class="px-2 py-1.5">
                <label class="inline-flex items-center gap-1.5 text-xs muse-text-body" @click.stop>
                  <Checkbox
                    :model-value="adapter.enabled"
                    @update:model-value="emit('toggle-enabled', adapter.id, Boolean($event))"
                  />
                  <span
                    class="muse-badge"
                    :class="adapter.enabled
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                      : 'border-stone-300/80 bg-stone-100 text-stone-600 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400'"
                  >
                    {{ adapter.enabled ? t('admin.providers.statusActive') : t('admin.providers.statusInactive') }}
                  </span>
                </label>
              </td>
              <td class="px-2 py-1.5 text-right">
                <div class="flex flex-wrap justify-end gap-1.5">
                  <Button size="sm" variant="secondary" @click="openEditModal(adapter)">{{ t('admin.common.edit') }}</Button>
                  <Button size="sm" variant="danger" @click="confirmDelete(adapter.id)">{{ t('admin.common.delete') }}</Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
