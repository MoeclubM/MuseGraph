<script setup lang="ts">
import { computed } from 'vue'
import type { PaymentConfig } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Checkbox from '@/components/ui/Checkbox.vue'

const props = defineProps<{
  paymentConfig: PaymentConfig
  paymentKeyInput: string
}>()

const emit = defineEmits<{
  'update:paymentKeyInput': [value: string]
  'save-payment': []
}>()

const paymentKeyInputValue = computed({
  get: () => props.paymentKeyInput,
  set: (value: string | number) => emit('update:paymentKeyInput', String(value || '')),
})
</script>

<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">EPay Config</h2>
      <p class="text-xs text-stone-500 dark:text-zinc-400">Manage recharge gateway settings.</p>
    </div>

    <Card class="space-y-3">
      <div class="grid gap-2 md:grid-cols-2">
        <label class="inline-flex items-center gap-2 rounded-md border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
          <Checkbox v-model="paymentConfig.enabled" />
          Enable EPay
        </label>
        <Select v-model="paymentConfig.payment_type">
          <option value="alipay">alipay</option>
          <option value="wxpay">wxpay</option>
          <option value="qqpay">qqpay</option>
        </Select>
        <Input v-model="paymentConfig.url" placeholder="Gateway URL (https://...)" />
        <Input v-model="paymentConfig.pid" placeholder="Merchant PID" />
        <Input
          v-model="paymentKeyInputValue"
          type="password"
          :placeholder="paymentConfig.has_key ? 'Key already set, leave blank to keep' : 'Communication key'"
        />
        <Input v-model="paymentConfig.notify_url" placeholder="Notify URL (optional)" />
        <Input v-model="paymentConfig.return_url" class="md:col-span-2" placeholder="Return URL (optional)" />
      </div>
      <div class="flex justify-end">
        <Button size="sm" @click="emit('save-payment')">Save</Button>
      </div>
    </Card>
  </div>
</template>
