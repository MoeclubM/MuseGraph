<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LlmRuntimeConfig, UsageRetentionConfig } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Select from '@/components/ui/Select.vue'

const { t } = useI18n()

const props = defineProps<{
  llmRuntimeConfig: LlmRuntimeConfig
  llmModelConcurrencyOverridesInput: string
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
  'update:llmModelConcurrencyOverridesInput': [value: string]
  'reload-usage-retention': []
  'save-usage-retention': []
  'run-usage-cleanup': []
  'update:usageRetention': [value: UsageRetentionConfig]
}>()

const llmModelConcurrencyOverridesInputValue = computed({
  get: () => props.llmModelConcurrencyOverridesInput,
  set: (value: string | number) => emit('update:llmModelConcurrencyOverridesInput', String(value || '')),
})
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
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_retry_count') }}</label>
          <Input v-model.number="llmRuntimeConfig.llm_retry_count" type="number" min="0" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_retry_interval_seconds') }}</label>
          <Input v-model.number="llmRuntimeConfig.llm_retry_interval_seconds" type="number" min="0" step="0.1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_task_concurrency') }}</label>
          <Input v-model.number="llmRuntimeConfig.llm_task_concurrency" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_model_default_concurrency') }}</label>
          <Input v-model.number="llmRuntimeConfig.llm_model_default_concurrency" type="number" min="1" />
        </div>
        <div class="space-y-1 md:col-span-3">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_fallback_model') }}</label>
          <Input v-model="llmRuntimeConfig.llm_fallback_model" type="text" />
        </div>
        <div class="space-y-1 md:col-span-3">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_model_concurrency_overrides') }}</label>
          <Textarea
            v-model="llmModelConcurrencyOverridesInputValue"
            :rows="4"
            :placeholder="t('admin.advanced.llmRequest.overridesPlaceholder')"
          />
        </div>
        <label class="inline-flex items-center gap-2 rounded-md border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
          <Checkbox v-model="llmRuntimeConfig.llm_prefer_stream" />
          {{ t('admin.advanced.fields.llm_prefer_stream') }}
        </label>
        <label class="inline-flex items-center gap-2 rounded-md border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
          <Checkbox v-model="llmRuntimeConfig.llm_stream_fallback_nonstream" />
          {{ t('admin.advanced.fields.llm_stream_fallback_nonstream') }}
        </label>
        <div class="space-y-1 md:col-span-3">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_openai_api_style') }}</label>
          <Select v-model="llmRuntimeConfig.llm_openai_api_style">
            <option value="responses">responses</option>
            <option value="chat_completions">chat_completions</option>
          </Select>
        </div>
        <div class="space-y-1 md:col-span-3">
          <label class="text-xs text-stone-500 dark:text-zinc-400">{{ t('admin.advanced.fields.llm_reasoning_effort') }}</label>
          <Select v-model="llmRuntimeConfig.llm_reasoning_effort">
            <option value="model_default">model_default</option>
            <option value="none">none</option>
            <option value="minimal">minimal</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="max">max</option>
            <option value="xhigh">xhigh</option>
          </Select>
          <p class="text-xs text-stone-500 dark:text-zinc-400">
            {{ t('admin.advanced.llmRequest.reasoningHint') }}
          </p>
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