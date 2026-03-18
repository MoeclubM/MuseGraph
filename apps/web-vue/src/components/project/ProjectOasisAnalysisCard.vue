<script setup lang="ts">
import { computed } from 'vue'
import { FileText, Network, Search, Sparkles } from 'lucide-vue-next'
import type { ModelInfo } from '@/api/projects'
import type { OasisTask } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Select from '@/components/ui/Select.vue'
import Textarea from '@/components/ui/Textarea.vue'

interface OasisPipelinePhase {
  key: string
  label: string
  done: boolean
}

const props = defineProps<{
  visible: boolean
  pipeline: OasisPipelinePhase[]
  models: ModelInfo[]
  modelsLoading: boolean
  graphReady: boolean
  hasOasisAnalysis: boolean
  oasisTaskPolling: boolean
  oasisPrepareLoading: boolean
  oasisTask: OasisTask | null
  oasisTaskLastId: string
  graphAnalysisLoading: boolean
  graphAnalysisError: string | null
  oasisPrepareError: string | null
  oasisTaskError: string | null
  graphAnalysisResult: string | null
  oasisPackage: Record<string, any> | null
  oasisRunResult: Record<string, any> | null
  oasisReport: Record<string, any> | null
  graphAnalysisPrompt: string
  oasisAnalysisModel: string
  oasisSimulationModel: string
  oasisReportModel: string
  oasisStageClass: (done: boolean) => string
  oasisTaskStatusColor: (status: string) => string
}>()

const emit = defineEmits<{
  'update:graphAnalysisPrompt': [value: string]
  'update:oasisAnalysisModel': [value: string]
  'update:oasisSimulationModel': [value: string]
  'update:oasisReportModel': [value: string]
  analyze: []
  prepare: []
  run: []
  report: []
  refreshStatus: []
}>()

const graphAnalysisPromptModel = computed({
  get: () => props.graphAnalysisPrompt,
  set: (value: string | number) => emit('update:graphAnalysisPrompt', String(value || '')),
})

const oasisAnalysisModelValue = computed({
  get: () => props.oasisAnalysisModel,
  set: (value: string | number) => emit('update:oasisAnalysisModel', String(value || '')),
})

const oasisSimulationModelValue = computed({
  get: () => props.oasisSimulationModel,
  set: (value: string | number) => emit('update:oasisSimulationModel', String(value || '')),
})

const oasisReportModelValue = computed({
  get: () => props.oasisReportModel,
  set: (value: string | number) => emit('update:oasisReportModel', String(value || '')),
})

const currentTaskLabel = computed(() => {
  const taskType = String(props.oasisTask?.task_type || '').toLowerCase()

  if (taskType === 'oasis_prepare') return 'package_prepare'
  if (taskType === 'oasis_run') return 'scenario_run'
  if (taskType === 'oasis_report') return 'analysis_report'

  return taskType || 'task'
})

const runtimeProfileCount = computed(() => Number(props.oasisPackage?.profiles?.length || 0))
const runtimeTriggerCount = computed(() => Number(props.oasisPackage?.simulation_config?.events?.length || 0))
const activeRoleCount = computed(() => Number(props.oasisRunResult?.metrics?.active_agents || 0))
const estimatedActivityCount = computed(() => Number(
  props.oasisRunResult?.metrics?.estimated_actions
  ?? props.oasisRunResult?.metrics?.estimated_events
  ?? props.oasisRunResult?.metrics?.estimated_posts
  ?? 0
))
</script>

<template>
  <Card v-show="visible" class="space-y-4">
    <h3 class="text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-zinc-400">
      Step 3. Scenario Reasoning
    </h3>
    <div class="grid grid-cols-4 gap-1.5">
      <div
        v-for="phase in props.pipeline"
        :key="phase.key"
        class="rounded border px-2 py-1 text-center text-[10px] uppercase tracking-wide"
        :class="props.oasisStageClass(phase.done)"
      >
        {{ phase.label }}
      </div>
    </div>
    <Textarea
      v-model="graphAnalysisPromptModel"
      :rows="2"
      placeholder="Describe the scenario analysis focus"
      class="min-h-24"
    />
    <div class="space-y-2">
      <label class="block text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-zinc-400">
        Analysis Model
      </label>
      <Select
        v-model="oasisAnalysisModelValue"
        :disabled="props.modelsLoading"
      >
        <option value="">Auto-select first configured model</option>
        <option v-for="m in props.models" :key="`oasis-analysis-${m.id}`" :value="m.id">{{ m.name }}</option>
      </Select>
    </div>
    <div class="space-y-2">
      <label class="block text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-zinc-400">
        Execution Model
      </label>
      <Select
        v-model="oasisSimulationModelValue"
        :disabled="props.modelsLoading"
      >
        <option value="">Auto-select first configured model</option>
        <option v-for="m in props.models" :key="`oasis-sim-${m.id}`" :value="m.id">{{ m.name }}</option>
      </Select>
    </div>
    <div class="space-y-2">
      <label class="block text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-zinc-400">
        Report Model
      </label>
      <Select
        v-model="oasisReportModelValue"
        :disabled="props.modelsLoading"
      >
        <option value="">Auto-select first configured model</option>
        <option v-for="m in props.models" :key="`oasis-report-${m.id}`" :value="m.id">{{ m.name }}</option>
      </Select>
    </div>
    <Button
      variant="secondary"
      class="w-full"
      :loading="props.graphAnalysisLoading"
      :disabled="!props.graphReady || props.oasisTaskPolling"
      @click="emit('analyze')"
    >
      <Search class="h-4 w-4" />
      Generate Scenario Analysis
    </Button>
    <Button
      variant="ghost"
      class="w-full"
      :loading="props.oasisPrepareLoading || (props.oasisTaskPolling && props.oasisTask?.task_type === 'oasis_prepare')"
      :disabled="!props.graphReady || !props.hasOasisAnalysis || props.oasisTaskPolling"
      @click="emit('prepare')"
    >
      <Sparkles class="h-4 w-4" />
      Prepare Runtime Package
    </Button>
    <Button
      variant="ghost"
      class="w-full"
      :loading="props.oasisTaskPolling && props.oasisTask?.task_type === 'oasis_run'"
      :disabled="!props.oasisPackage || props.oasisTaskPolling"
      @click="emit('run')"
    >
      <Network class="h-4 w-4" />
      Execute Scenario Run
    </Button>
    <Button
      variant="ghost"
      class="w-full"
      :loading="props.oasisTaskPolling && props.oasisTask?.task_type === 'oasis_report'"
      :disabled="!props.oasisRunResult || props.oasisTaskPolling"
      @click="emit('report')"
    >
      <FileText class="h-4 w-4" />
      Generate Analysis Report
    </Button>
    <p v-if="!props.graphReady" class="text-xs text-amber-700 dark:text-amber-300">Build the graph before starting scenario analysis.</p>
    <Alert v-if="props.graphAnalysisError" variant="destructive" class="text-sm">
      {{ props.graphAnalysisError }}
    </Alert>
    <Alert v-if="props.oasisPrepareError" variant="destructive" class="text-sm">
      {{ props.oasisPrepareError }}
    </Alert>
    <Alert v-if="props.oasisTaskError" variant="destructive" class="text-sm">
      {{ props.oasisTaskError }}
    </Alert>
    <div
      v-if="props.oasisTask"
      class="space-y-2 rounded-lg border border-stone-300/80 bg-stone-100/75 p-3 text-xs text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/40 dark:text-zinc-200"
    >
      <div class="flex items-center justify-between">
        <span class="uppercase tracking-wider text-stone-500 dark:text-zinc-400">{{ currentTaskLabel }}</span>
        <span class="capitalize" :class="props.oasisTaskStatusColor(props.oasisTask.status)">{{ props.oasisTask.status }}</span>
      </div>
      <p class="text-stone-700 dark:text-zinc-300">{{ props.oasisTask.message || 'Processing...' }}</p>
      <div class="h-1.5 overflow-hidden rounded bg-stone-200/70 dark:bg-zinc-800/70">
        <div
          class="h-full bg-amber-500 transition-all duration-300"
          :style="{ width: `${props.oasisTask.progress || 0}%` }"
        />
      </div>
      <div class="flex items-center justify-between gap-2 text-[11px] text-stone-500 dark:text-zinc-400">
        <span>Task ID: {{ props.oasisTask.task_id }}</span>
        <Button
          variant="secondary"
          size="sm"
          :disabled="props.oasisTaskPolling"
          @click="emit('refreshStatus')"
        >
          Refresh status
        </Button>
      </div>
    </div>
    <div
      v-if="!props.oasisTask && props.oasisTaskLastId"
      class="space-y-2 rounded-lg border border-stone-300/80 bg-stone-100/75 p-3 text-xs text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/40 dark:text-zinc-300"
    >
      <p>Last scenario task: {{ props.oasisTaskLastId }}</p>
      <Button
        variant="secondary"
        size="sm"
        :disabled="props.oasisTaskPolling"
        @click="emit('refreshStatus')"
      >
        Refresh last task status
      </Button>
    </div>
    <div
      v-if="props.graphAnalysisResult"
      class="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg border border-stone-300/80 bg-stone-100/75 p-3 text-sm text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/40 dark:text-zinc-200"
    >
      {{ props.graphAnalysisResult }}
    </div>
    <div
      v-if="props.hasOasisAnalysis"
      class="rounded-lg border border-emerald-300/70 bg-emerald-100 p-3 text-xs text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300"
    >
      Scenario analysis is ready. Guidance and analysis profiles are now available for continuation workflows.
    </div>
    <div
      v-if="props.oasisPackage"
      class="space-y-1 rounded-lg border border-amber-700/30 bg-amber-900/10 p-3 text-xs text-amber-800 dark:text-amber-200"
    >
      <p>Runtime Package: {{ props.oasisPackage.simulation_id }}</p>
      <p>Analysis Profiles: {{ runtimeProfileCount }}</p>
      <p>Scenario Triggers: {{ runtimeTriggerCount }}</p>
    </div>
    <div
      v-if="props.oasisRunResult"
      class="space-y-1 rounded-lg border border-stone-300/80 bg-stone-100/75 p-3 text-xs text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/40 dark:text-zinc-200"
    >
      <p>Run: {{ props.oasisRunResult.run_id }}</p>
      <p>Rounds: {{ props.oasisRunResult.metrics?.total_rounds || 0 }}</p>
      <p>Active Roles: {{ activeRoleCount }}</p>
      <p>Estimated Activity Items: {{ estimatedActivityCount }}</p>
    </div>
    <div
      v-if="props.oasisReport"
      class="space-y-1 rounded-lg border border-amber-300/80 bg-amber-100/75 p-3 text-xs text-amber-900 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-200"
    >
      <p>Report: {{ props.oasisReport.report_id }}</p>
      <p class="font-medium">{{ props.oasisReport.title }}</p>
      <p class="line-clamp-3 text-amber-800 dark:text-amber-200/90">{{ props.oasisReport.executive_summary }}</p>
    </div>
  </Card>
</template>
