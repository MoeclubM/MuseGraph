<script setup lang="ts">
import { computed } from 'vue'
import type { PricingRule, Provider } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Checkbox from '@/components/ui/Checkbox.vue'

type ProviderModelKind = 'chat' | 'embedding'

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
  providerNameForModel: (model: string) => string
  modelTypeForModel: (model: string) => string
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
  'remove-model': [model: string]
  'new-pricing': [model: string]
  'edit-pricing': [rule: PricingRule]
  'update:showPricingForm': [value: boolean]
  'save-pricing': []
}>()

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
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
      <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Models & Pricing</h2>
      <div class="flex flex-wrap items-center gap-2 sm:flex-nowrap">
        <span class="text-xs text-stone-500 dark:text-zinc-400">Token billing unit is fixed at 1M.</span>
        <Button size="sm" @click="emit('open-model-form')">Add Model</Button>
      </div>
    </div>

    <Card v-if="showModelForm" class="space-y-3">
      <div class="grid gap-2 md:grid-cols-4">
        <Select v-model="providerModelProviderIdValue" class="md:col-span-2">
          <option value="">Select provider</option>
          <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
        </Select>
        <Select v-model="providerModelFormKindValue">
          <option value="chat">LLM</option>
          <option value="embedding">Embedding</option>
        </Select>
        <div class="flex gap-2">
          <Button size="sm" variant="secondary" class="flex-1" @click="emit('refresh-discover', providerModelFormKind, false)">Discover</Button>
          <Button size="sm" class="flex-1" @click="emit('refresh-discover', providerModelFormKind, true)">Import</Button>
        </div>
      </div>

      <div class="grid gap-2 md:grid-cols-3">
        <div class="flex gap-2 md:col-span-2">
          <Select v-model="discoveredModelForCurrentKindValue" class="flex-1">
            <option value="">Select discovered</option>
            <option v-for="m in discoveredModelsForCurrentKind" :key="m" :value="m">{{ m }}</option>
          </Select>
          <Button size="sm" variant="secondary" @click="emit('add-model-discovered')">
            {{ providerModelFormKind === 'embedding' ? 'Add Embedding' : 'Add Model' }}
          </Button>
        </div>
        <div class="flex gap-2">
          <Input
            v-model="providerModelManualInputValue"
            class="flex-1"
            :placeholder="providerModelFormKind === 'embedding' ? 'Manual embedding model id' : 'Manual model id'"
          />
          <Button size="sm" variant="secondary" @click="emit('add-model-manual')">
            {{ providerModelFormKind === 'embedding' ? 'Add Embedding' : 'Add Model' }}
          </Button>
        </div>
      </div>

      <Alert v-if="providerModelErrorForCurrentKind" variant="destructive">{{ providerModelErrorForCurrentKind }}</Alert>
      <Alert v-if="providerModelMessageForCurrentKind" variant="success">{{ providerModelMessageForCurrentKind }}</Alert>

      <div class="flex justify-end">
        <Button size="sm" variant="secondary" @click="emit('close-model-form')">Close</Button>
      </div>
    </Card>

    <Card v-if="showPricingForm" class="space-y-3">
      <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">Pricing Rule</h3>
      <div class="grid gap-2 md:grid-cols-2">
        <Input list="known-models" v-model="pricingForm.model" placeholder="Model" />
        <Select v-model="pricingForm.billing_mode">
          <option value="TOKEN">TOKEN</option>
          <option value="REQUEST">REQUEST</option>
        </Select>

        <template v-if="pricingForm.billing_mode === 'TOKEN'">
          <Input v-model.number="pricingForm.input_price" type="number" min="0" step="0.000001" placeholder="Input Price" />
          <Input v-model.number="pricingForm.output_price" type="number" min="0" step="0.000001" placeholder="Output Price" />
          <div class="rounded-md border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-600 md:col-span-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
            Token Unit: 1,000,000 (fixed)
          </div>
        </template>

        <Input
          v-else
          v-model.number="pricingForm.request_price"
          type="number"
          min="0"
          step="0.000001"
          class="md:col-span-2"
          placeholder="Price Per Request"
        />

        <label class="inline-flex items-center gap-2 rounded-md border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 md:col-span-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
          <Checkbox v-model="pricingForm.is_active" />
          Active
        </label>
      </div>

      <datalist id="known-models">
        <option v-for="m in knownModels" :key="m" :value="m">{{ m }}</option>
      </datalist>

      <Alert v-if="pricingFormError" variant="destructive">{{ pricingFormError }}</Alert>

      <div class="flex justify-end gap-2">
        <Button size="sm" variant="secondary" @click="emit('update:showPricingForm', false)">Cancel</Button>
        <Button size="sm" @click="emit('save-pricing')">Save</Button>
      </div>
    </Card>

    <Card :stack="false">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
            <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
              <tr class="border-b border-stone-300 dark:border-zinc-700">
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Model</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Provider</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Type</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Mode</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Pricing</th>
                <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Action</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="model in knownModels"
                :key="model"
                class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
              >
                <td class="px-3 py-2 font-mono text-xs text-stone-700 dark:text-zinc-200">{{ model }}</td>
                <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ providerNameForModel(model) }}</td>
                <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ modelTypeForModel(model) }}</td>
                <td class="px-3 py-2">
                  <span class="inline-flex rounded-full border border-stone-300 bg-stone-100 px-2 py-0.5 text-xs text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                    {{ pricingByModel(model)?.billing_mode || 'N/A' }}
                  </span>
                </td>
                <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ formatPricing(pricingByModel(model)) }}</td>
                <td class="px-3 py-2 text-right">
                  <div class="flex flex-wrap justify-end gap-2">
                    <Button size="sm" variant="secondary" @click="pricingByModel(model) ? emit('edit-pricing', pricingByModel(model)!) : emit('new-pricing', model)">
                      {{ pricingByModel(model) ? 'Edit' : 'Set' }}
                    </Button>
                    <Button size="sm" variant="danger" @click="emit('remove-model', model)">Delete</Button>
                  </div>
                </td>
              </tr>
            </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
