<script setup lang="ts">
import { computed } from 'vue'
import type { OasisConfig } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Checkbox from '@/components/ui/Checkbox.vue'

const props = defineProps<{
  oasisConfig: OasisConfig
  llmModelConcurrencyOverridesInput: string
  llmRequestConfigError: string
  llmRequestConfigMessage: string
  oasisAdvancedConfigError: string
  oasisAdvancedConfigMessage: string
}>()

const emit = defineEmits<{
  'reload-llm-request-config': []
  'save-llm-request-config': []
  'reload-oasis-advanced-config': []
  'save-oasis-advanced-config': []
  'update:llmModelConcurrencyOverridesInput': [value: string]
}>()

const llmModelConcurrencyOverridesInputValue = computed({
  get: () => props.llmModelConcurrencyOverridesInput,
  set: (value: string | number) => emit('update:llmModelConcurrencyOverridesInput', String(value || '')),
})
</script>

<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Advanced Settings</h2>
      <p class="text-xs text-stone-500 dark:text-zinc-400">LLM request settings and scenario reasoning limits.</p>
    </div>

    <Card class="space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
        <div>
          <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">LLM Request Config</h3>
          <p class="text-xs text-stone-500 dark:text-zinc-400">Configure timeout, retry count, and concurrency.</p>
        </div>
        <Button size="sm" variant="secondary" @click="emit('reload-llm-request-config')">Refresh</Button>
      </div>

      <div class="grid gap-2 md:grid-cols-3">
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">llm_request_timeout_seconds</label>
          <Input v-model.number="oasisConfig.llm_request_timeout_seconds" type="number" min="5" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">llm_retry_count</label>
          <Input v-model.number="oasisConfig.llm_retry_count" type="number" min="0" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">llm_retry_interval_seconds</label>
          <Input v-model.number="oasisConfig.llm_retry_interval_seconds" type="number" min="0" step="0.1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">llm_task_concurrency</label>
          <Input v-model.number="oasisConfig.llm_task_concurrency" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">llm_model_default_concurrency</label>
          <Input v-model.number="oasisConfig.llm_model_default_concurrency" type="number" min="1" />
        </div>
        <div class="space-y-1 md:col-span-3">
          <label class="text-xs text-stone-500 dark:text-zinc-400">llm_model_concurrency_overrides (JSON object)</label>
          <Textarea
            v-model="llmModelConcurrencyOverridesInputValue"
            :rows="4"
            placeholder='{"gpt-4o-mini": 4, "claude-3-7-sonnet": 2}'
          />
        </div>
        <label class="inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
          <Checkbox v-model="oasisConfig.llm_prefer_stream" />
          llm_prefer_stream
        </label>
        <label class="inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
          <Checkbox v-model="oasisConfig.llm_stream_fallback_nonstream" />
          llm_stream_fallback_nonstream
        </label>
      </div>

      <Alert v-if="llmRequestConfigError" variant="destructive">{{ llmRequestConfigError }}</Alert>
      <Alert v-if="llmRequestConfigMessage" variant="success">{{ llmRequestConfigMessage }}</Alert>

      <div class="flex justify-end">
        <Button size="sm" @click="emit('save-llm-request-config')">Save LLM Request Config</Button>
      </div>
    </Card>

    <Card class="space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
        <div>
          <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">Scenario Reasoning Config</h3>
          <p class="text-xs text-stone-500 dark:text-zinc-400">Configure analysis prompts, iteration cadence, and activity limits.</p>
        </div>
        <Button size="sm" variant="secondary" @click="emit('reload-oasis-advanced-config')">Refresh</Button>
      </div>

      <div class="grid gap-2 md:grid-cols-2">
        <div class="space-y-1 md:col-span-2">
          <label class="text-xs text-stone-500 dark:text-zinc-400">analysis prompt prefix</label>
          <Textarea
            v-model="oasisConfig.analysis_prompt_prefix"
            :rows="3"
            placeholder="analysis prompt prefix"
          />
        </div>
        <div class="space-y-1 md:col-span-2">
          <label class="text-xs text-stone-500 dark:text-zinc-400">runtime prompt prefix</label>
          <Textarea
            v-model="oasisConfig.simulation_prompt_prefix"
            :rows="3"
            placeholder="runtime prompt prefix"
          />
        </div>
        <div class="space-y-1 md:col-span-2">
          <label class="text-xs text-stone-500 dark:text-zinc-400">report prompt prefix</label>
          <Textarea
            v-model="oasisConfig.report_prompt_prefix"
            :rows="3"
            placeholder="report prompt prefix"
          />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">max_agent_profiles</label>
          <Input v-model.number="oasisConfig.max_agent_profiles" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">max_events</label>
          <Input v-model.number="oasisConfig.max_events" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">max_agent_activity</label>
          <Input v-model.number="oasisConfig.max_agent_activity" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">min_total_hours</label>
          <Input v-model.number="oasisConfig.min_total_hours" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">max_total_hours</label>
          <Input v-model.number="oasisConfig.max_total_hours" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">min_minutes_per_round</label>
          <Input v-model.number="oasisConfig.min_minutes_per_round" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">max_minutes_per_round</label>
          <Input v-model.number="oasisConfig.max_minutes_per_round" type="number" min="1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">max_actions_per_hour</label>
          <Input v-model.number="oasisConfig.max_actions_per_hour" type="number" min="0.2" step="0.1" />
        </div>
        <div class="space-y-1">
          <label class="text-xs text-stone-500 dark:text-zinc-400">max_response_delay_minutes</label>
          <Input v-model.number="oasisConfig.max_response_delay_minutes" type="number" min="1" />
        </div>
      </div>

      <Alert v-if="oasisAdvancedConfigError" variant="destructive">{{ oasisAdvancedConfigError }}</Alert>
      <Alert v-if="oasisAdvancedConfigMessage" variant="success">{{ oasisAdvancedConfigMessage }}</Alert>

      <div class="flex justify-end">
        <Button size="sm" @click="emit('save-oasis-advanced-config')">Save Scenario Config</Button>
      </div>
    </Card>
  </div>
</template>
