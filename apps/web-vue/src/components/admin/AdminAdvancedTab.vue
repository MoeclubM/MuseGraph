<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { LlmRuntimeConfig, UsageRetentionConfig } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'

const { t } = useI18n()

const props = defineProps<{
  llmRuntimeConfig: LlmRuntimeConfig
  llmRequestConfigError: string
  llmRequestConfigMessage: string
  usageRetention: UsageRetentionConfig
  usageRetentionError: string
  usageRetentionMessage: string
  usageCleanupMessage: string
}>()

const emit = defineEmits<{
  'reload-llm-request-config': []
  'save-llm-request-config': []
  'reload-usage-retention': []
  'save-usage-retention': []
  'run-usage-cleanup': []
  'update:usageRetention': [value: UsageRetentionConfig]
}>()

</script>

<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">{{ t('admin.advanced.title') }}</h2>
      <p class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.subtitle') }}</p>
    </div>

    <Card class="space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
        <div>
          <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">{{ t('admin.advanced.llmRequest.title') }}</h3>
          <p class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.llmRequest.hint') }}</p>
        </div>
        <Button size="sm" variant="secondary" @click="emit('reload-llm-request-config')">{{ t('common.refresh') }}</Button>
      </div>

      <div class="grid gap-2 md:grid-cols-3">
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_request_timeout_seconds') }}</label>
          <Input v-model.number="llmRuntimeConfig.llm_request_timeout_seconds" type="number" min="5" />
        </div>
      </div>

      <Alert v-if="llmRequestConfigError" variant="destructive">{{ llmRequestConfigError }}</Alert>
      <Alert v-if="llmRequestConfigMessage" variant="success">{{ llmRequestConfigMessage }}</Alert>

      <div class="flex justify-end">
        <Button size="sm" @click="emit('save-llm-request-config')">{{ t('admin.advanced.llmRequest.save') }}</Button>
      </div>
    </Card>

    <Card class="space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
        <div>
          <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">{{ t('admin.advanced.usageRetention.title') }}</h3>
          <p class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.usageRetention.hint') }}</p>
        </div>
        <Button size="sm" variant="secondary" @click="emit('reload-usage-retention')">{{ t('common.refresh') }}</Button>
      </div>
      <div class="grid gap-2 md:grid-cols-2">
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.usageRetention.retentionDays') }}</label>
          <Input
            :model-value="usageRetention.retention_days ?? ''"
            type="number"
            min="1"
            :placeholder="t('admin.advanced.usageRetention.unlimitedPlaceholder')"
            @update:model-value="
              emit('update:usageRetention', {
                ...usageRetention,
                retention_days: $event === '' || $event == null ? null : Number($event),
              })
            "
          />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.usageRetention.maxRecords') }}</label>
          <Input
            :model-value="usageRetention.max_records ?? ''"
            type="number"
            min="1"
            :placeholder="t('admin.advanced.usageRetention.unlimitedPlaceholder')"
            @update:model-value="
              emit('update:usageRetention', {
                ...usageRetention,
                max_records: $event === '' || $event == null ? null : Number($event),
              })
            "
          />
        </div>
      </div>
      <p class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.usageRetention.note') }}</p>
      <Alert v-if="usageRetentionError" variant="destructive">{{ usageRetentionError }}</Alert>
      <Alert v-if="usageRetentionMessage" variant="success">{{ usageRetentionMessage }}</Alert>
      <Alert v-if="usageCleanupMessage" variant="success">{{ usageCleanupMessage }}</Alert>
      <div class="flex flex-wrap justify-end gap-2">
        <Button size="sm" variant="secondary" @click="emit('run-usage-cleanup')">
          {{ t('admin.advanced.usageRetention.runCleanup') }}
        </Button>
        <Button size="sm" @click="emit('save-usage-retention')">{{ t('admin.advanced.usageRetention.save') }}</Button>
      </div>
    </Card>
  </div>
</template>
