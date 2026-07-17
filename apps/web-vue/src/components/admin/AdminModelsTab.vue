<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PricingRule, Provider } from '@/types'
import Card from '@/components/ui/Card.vue'
import Modal from '@/components/ui/Modal.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import AdminFormField from '@/components/admin/AdminFormField.vue'

type ProviderModelKind = 'chat' | 'embedding' | 'reranker'
type ModelRow = {
  providerId: string
  providerName: string
  kind: ProviderModelKind
  model: string
}

interface PricingForm {
  id: string
  model: string
  billing_mode: 'TOKEN' | 'REQUEST'
  input_price: number
  output_price: number
  request_price: number
  is_active: boolean
}

const props = defineProps<{
  providers: Provider[]
  knownModels: string[]
  showModelForm: boolean
  providerModelProviderId: string
  providerModelFormKind: ProviderModelKind
  providerModelManualInput: string
  discoveredModelsForCurrentKind: string[]
  discoveredModelForCurrentKind: string
  providerModelErrorForCurrentKind: string
  providerModelMessageForCurrentKind: string
  showPricingForm: boolean
  pricingForm: PricingForm
  pricingFormError: string
  formatPricing: (rule?: PricingRule) => string
  pricingByModel: (model: string) => PricingRule | undefined
  modelRows: ModelRow[]
}>()

const emit = defineEmits<{
  'open-model-form': []
  'close-model-form': []
  'update:providerModelProviderId': [value: string]
  'update:providerModelFormKind': [value: ProviderModelKind]
  'refresh-discover': [kind: ProviderModelKind, persist: boolean]
  'update:discoveredModelForCurrentKind': [value: string]
  'add-model-discovered': []
  'update:providerModelManualInput': [value: string]
  'add-model-manual': []
  'remove-model-binding': [row: ModelRow]
  'new-pricing': [model: string]
  'edit-pricing': [rule: PricingRule]
  'update:showPricingForm': [value: boolean]
  'save-pricing': []
}>()

const { t } = useI18n()

const searchQuery = ref('')
const providerFilter = ref('')
const kindFilter = ref<'' | ProviderModelKind>('')
const billingFilter = ref<'' | 'TOKEN' | 'REQUEST' | 'NONE'>('')

const providerModelProviderIdValue = computed({
  get: () => props.providerModelProviderId,
  set: (value: string | number) => emit('update:providerModelProviderId', String(value || '')),
})

const providerModelFormKindValue = computed({
  get: () => props.providerModelFormKind,
  set: (value: string | number) => emit('update:providerModelFormKind', String(value || 'chat') as ProviderModelKind),
})

const discoveredModelForCurrentKindValue = computed({
  get: () => props.discoveredModelForCurrentKind,
  set: (value: string | number) => emit('update:discoveredModelForCurrentKind', String(value || '')),
})

const providerModelManualInputValue = computed({
  get: () => props.providerModelManualInput,
  set: (value: string | number) => emit('update:providerModelManualInput', String(value || '')),
})

const filteredRows = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return props.modelRows.filter((row) => {
    if (query) {
      const haystack = `${row.model} ${row.providerName}`.toLowerCase()
      if (!haystack.includes(query)) return false
    }
    if (providerFilter.value && row.providerId !== providerFilter.value) return false
    if (kindFilter.value && row.kind !== kindFilter.value) return false
    if (billingFilter.value) {
      const mode = props.pricingByModel(row.model)?.billing_mode
      if (billingFilter.value === 'NONE') return !mode
      return mode === billingFilter.value
    }
    return true
  })
})

function kindLabel(kind: ProviderModelKind): string {
  if (kind === 'embedding') return t('admin.models.kindEmbedding')
  if (kind === 'reranker') return t('admin.models.kindReranker')
  return t('admin.models.kindLlm')
}

function addModelLabel(): string {
  if (props.providerModelFormKind === 'embedding') return t('admin.models.addEmbedding')
  if (props.providerModelFormKind === 'reranker') return t('admin.models.addReranker')
  return t('admin.models.addModel')
}

function manualPlaceholder(): string {
  if (props.providerModelFormKind === 'embedding') return t('admin.models.manualEmbeddingPlaceholder')
  if (props.providerModelFormKind === 'reranker') return t('admin.models.manualRerankerPlaceholder')
  return t('admin.models.manualLlmPlaceholder')
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-2">
      <div>
        <h2 class="text-sm font-semibold muse-text-heading">{{ t('admin.models.title') }}</h2>
        <p class="text-xs muse-text-muted">
          {{ t('admin.models.filters.resultCount', { shown: filteredRows.length, total: modelRows.length }) }}
          · {{ t('admin.models.tokenUnitHint') }}
        </p>
      </div>
      <Button size="sm" @click="emit('open-model-form')">{{ t('admin.models.addModel') }}</Button>
    </div>

    <Card variant="inset" class="muse-card-compact">
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <AdminFormField :label="t('admin.models.filters.searchLabel')">
          <Input
            v-model="searchQuery"
            size="sm"
            :placeholder="t('admin.models.filters.searchModel')"
          />
        </AdminFormField>
        <AdminFormField :label="t('admin.models.filters.providerLabel')">
          <Select v-model="providerFilter" size="sm" :aria-label="t('admin.models.filters.providerLabel')">
            <option value="">{{ t('admin.models.filters.allProviders') }}</option>
            <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
          </Select>
        </AdminFormField>
        <AdminFormField :label="t('admin.models.filters.typeLabel')">
          <Select v-model="kindFilter" size="sm" :aria-label="t('admin.models.filters.typeLabel')">
            <option value="">{{ t('admin.models.filters.allTypes') }}</option>
            <option value="chat">{{ t('admin.models.kindLlm') }}</option>
            <option value="embedding">{{ t('admin.models.kindEmbedding') }}</option>
            <option value="reranker">{{ t('admin.models.kindReranker') }}</option>
          </Select>
        </AdminFormField>
        <AdminFormField :label="t('admin.models.filters.billingLabel')">
          <Select v-model="billingFilter" size="sm" :aria-label="t('admin.models.filters.billingLabel')">
            <option value="">{{ t('admin.models.filters.allBilling') }}</option>
            <option value="TOKEN">{{ t('admin.models.billingToken') }}</option>
            <option value="REQUEST">{{ t('admin.models.billingRequest') }}</option>
            <option value="NONE">{{ t('admin.models.filters.billingNone') }}</option>
          </Select>
        </AdminFormField>
      </div>
    </Card>

    <Modal
      :show="showModelForm"
      size="xl"
      :title="t('admin.models.addModelFormTitle')"
      @close="emit('close-model-form')"
    >
      <div class="space-y-4">
        <p class="text-xs muse-text-muted">{{ t('admin.models.addModelFormSubtitle') }}</p>

      <div class="space-y-3">
        <p class="text-xs font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.models.sectionBindTarget') }}</p>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <AdminFormField
            class="md:col-span-2 xl:col-span-2"
            :label="t('admin.models.selectProvider')"
            :description="t('admin.models.providerHint')"
          >
            <Select
              v-model="providerModelProviderIdValue"
              size="md"
              :aria-label="t('admin.models.selectProvider')"
            >
              <option value="">{{ t('admin.models.selectProvider') }}</option>
              <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
            </Select>
          </AdminFormField>
          <AdminFormField
            :label="t('admin.models.modelKind')"
            :description="t('admin.models.modelKindHint')"
          >
            <Select
              v-model="providerModelFormKindValue"
              size="md"
              :aria-label="t('admin.models.modelKind')"
            >
              <option value="chat">{{ t('admin.models.kindLlm') }}</option>
              <option value="embedding">{{ t('admin.models.kindEmbedding') }}</option>
              <option value="reranker">{{ t('admin.models.kindReranker') }}</option>
            </Select>
          </AdminFormField>
          <div class="flex flex-col justify-end gap-1.5">
            <p class="text-xs muse-text-muted">{{ t('admin.models.discoverHint') }}</p>
            <div class="flex gap-2">
              <Button size="sm" variant="secondary" class="flex-1" @click="emit('refresh-discover', providerModelFormKind, false)">{{ t('admin.models.discover') }}</Button>
              <Button size="sm" class="flex-1" @click="emit('refresh-discover', providerModelFormKind, true)">{{ t('admin.models.import') }}</Button>
            </div>
          </div>
        </div>
      </div>

      <div class="space-y-3">
        <p class="text-xs font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.models.sectionDiscover') }}</p>
        <AdminFormField
          :label="t('admin.models.selectDiscovered')"
          :description="t('admin.models.discoveredHint')"
        >
          <div class="flex gap-2">
            <Select
              v-model="discoveredModelForCurrentKindValue"
              size="md"
              class="flex-1"
              :aria-label="t('admin.models.selectDiscovered')"
            >
              <option value="">{{ t('admin.models.selectDiscovered') }}</option>
              <option v-for="m in discoveredModelsForCurrentKind" :key="m" :value="m">{{ m }}</option>
            </Select>
            <Button size="sm" variant="secondary" class="shrink-0" @click="emit('add-model-discovered')">{{ addModelLabel() }}</Button>
          </div>
        </AdminFormField>
      </div>

      <div class="space-y-3">
        <p class="text-xs font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.models.sectionManual') }}</p>
        <AdminFormField
          :label="t('admin.models.manualModelId')"
          :description="t('admin.models.manualHint')"
        >
          <div class="flex gap-2">
            <Input
              v-model="providerModelManualInputValue"
              class="flex-1"
              size="sm"
              :placeholder="manualPlaceholder()"
            />
            <Button size="sm" variant="secondary" class="shrink-0" @click="emit('add-model-manual')">{{ addModelLabel() }}</Button>
          </div>
        </AdminFormField>
      </div>

      <Alert v-if="providerModelErrorForCurrentKind" variant="destructive">{{ providerModelErrorForCurrentKind }}</Alert>
      <Alert v-if="providerModelMessageForCurrentKind" variant="success">{{ providerModelMessageForCurrentKind }}</Alert>

      <div class="flex justify-end border-t border-[color:var(--muse-border)] pt-3">
        <Button size="sm" variant="secondary" @click="emit('close-model-form')">{{ t('admin.common.close') }}</Button>
      </div>
      </div>
    </Modal>

    <Modal
      :show="showPricingForm"
      size="lg"
      :title="t('admin.models.pricingRule')"
      @close="emit('update:showPricingForm', false)"
    >
      <div class="space-y-4">
        <p class="text-xs muse-text-muted">{{ t('admin.models.pricingRuleSubtitle') }}</p>
      <div class="grid gap-3 md:grid-cols-2">
        <AdminFormField
          :label="t('admin.models.pricingModel')"
          :description="t('admin.models.pricingModelHint')"
        >
          <Input
            list="known-models"
            v-model="pricingForm.model"
            size="sm"
            :placeholder="t('admin.models.manualLlmPlaceholder')"
          />
        </AdminFormField>
        <AdminFormField
          :label="t('admin.models.billingMode')"
          :description="t('admin.models.billingModeHint')"
        >
          <Select v-model="pricingForm.billing_mode" size="md" :aria-label="t('admin.models.billingMode')">
            <option value="TOKEN">{{ t('admin.models.billingToken') }}</option>
            <option value="REQUEST">{{ t('admin.models.billingRequest') }}</option>
          </Select>
        </AdminFormField>

        <template v-if="pricingForm.billing_mode === 'TOKEN'">
          <AdminFormField
            :label="t('admin.models.inputPrice')"
            :description="t('admin.models.inputPriceHint')"
          >
            <Input
              v-model.number="pricingForm.input_price"
              type="number"
              min="0"
              step="0.000001"
              placeholder="0"
              size="sm"
            />
          </AdminFormField>
          <AdminFormField
            :label="t('admin.models.outputPrice')"
            :description="t('admin.models.outputPriceHint')"
          >
            <Input
              v-model.number="pricingForm.output_price"
              type="number"
              min="0"
              step="0.000001"
              placeholder="0"
              size="sm"
            />
          </AdminFormField>
          <p class="text-xs muse-text-muted md:col-span-2">
            {{ t('admin.models.tokenUnitFixed') }}
          </p>
        </template>

        <AdminFormField
          v-else
          class="md:col-span-2"
          :label="t('admin.models.pricePerRequest')"
          :description="t('admin.models.pricePerRequestHint')"
        >
          <Input
            v-model.number="pricingForm.request_price"
            type="number"
            min="0"
            step="0.000001"
            placeholder="0"
            size="sm"
          />
        </AdminFormField>

        <label class="flex items-start justify-between gap-3 rounded-md border border-[color:var(--muse-border)] bg-[color:var(--muse-field)] px-3 py-2.5 md:col-span-2">
          <div class="min-w-0">
            <p class="text-sm font-medium muse-text-body">{{ t('admin.models.pricingActive') }}</p>
            <p class="mt-0.5 text-xs muse-text-muted">{{ t('admin.models.pricingActiveHint') }}</p>
          </div>
          <Checkbox v-model="pricingForm.is_active" class="mt-0.5 shrink-0" />
        </label>
      </div>

      <datalist id="known-models">
        <option v-for="m in knownModels" :key="m" :value="m">{{ m }}</option>
      </datalist>

      <Alert v-if="pricingFormError" variant="destructive">{{ pricingFormError }}</Alert>

      <div class="flex justify-end gap-2 border-t border-[color:var(--muse-border)] pt-3">
        <Button size="sm" variant="secondary" @click="emit('update:showPricingForm', false)">{{ t('common.cancel') }}</Button>
        <Button size="sm" @click="emit('save-pricing')">{{ t('common.save') }}</Button>
      </div>
      </div>
    </Modal>

    <Card variant="compact" :stack="false">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-[color:var(--muse-bg-soft)]">
            <tr class="border-b border-[color:var(--muse-border)]">
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.models.columns.model') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.models.columns.provider') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.models.columns.type') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.models.columns.mode') }}</th>
              <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.models.columns.pricing') }}</th>
              <th class="px-2 py-1.5 text-right text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.common.action') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in filteredRows"
              :key="`${row.providerId}:${row.kind}:${row.model}`"
              class="border-b border-[color:var(--muse-border)] transition-colors hover:bg-[color:var(--muse-field-hover)]"
            >
              <td class="px-2 py-1.5 font-mono text-[11px] muse-text-body">{{ row.model }}</td>
              <td class="px-2 py-1.5 text-xs muse-text-muted">{{ row.providerName }}</td>
              <td class="px-2 py-1.5 text-xs muse-text-muted">{{ kindLabel(row.kind) }}</td>
              <td class="px-2 py-1.5">
                <span class="muse-badge border-[color:var(--muse-border)] bg-[color:var(--muse-field)] text-[color:var(--muse-text-muted)]">
                  {{ pricingByModel(row.model)?.billing_mode === 'TOKEN' ? t('admin.models.billingToken') : pricingByModel(row.model)?.billing_mode === 'REQUEST' ? t('admin.models.billingRequest') : t('admin.common.na') }}
                </span>
              </td>
              <td class="px-2 py-1.5 text-xs muse-text-muted">{{ formatPricing(pricingByModel(row.model)) }}</td>
              <td class="px-2 py-1.5 text-right">
                <div class="flex flex-wrap justify-end gap-1.5">
                  <Button
                    size="sm"
                    variant="secondary"
                    @click="pricingByModel(row.model) ? emit('edit-pricing', pricingByModel(row.model)!) : emit('new-pricing', row.model)"
                  >
                    {{ pricingByModel(row.model) ? t('admin.common.edit') : t('admin.common.set') }}
                  </Button>
                  <Button size="sm" variant="danger" @click="emit('remove-model-binding', row)">{{ t('admin.common.remove') }}</Button>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredRows.length">
              <td colspan="6" class="px-2 py-6 text-center text-xs muse-text-muted">{{ t('admin.models.filters.noResults') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>