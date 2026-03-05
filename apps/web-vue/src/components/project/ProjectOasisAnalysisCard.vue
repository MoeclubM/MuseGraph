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
</script>

<template>
  <Card v-show="visible" class="space-y-4">
    <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
      Step 3. OASIS Analysis
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
      placeholder="Enter OASIS analysis focus"
      class="min-h-24"
    />
    <div class="space-y-2">
      <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
        OASIS Analysis Model
      </label>
      <Select
        v-model="oasisAnalysisModelValue"
        :disabled="props.modelsLoading"
      >
        <option value="">Use backend default</option>
        <option v-for="m in props.models" :key="`oasis-analysis-${m.id}`" :value="m.id">{{ m.name }}</option>
      </Select>
    </div>
    <div class="space-y-2">
      <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
        OASIS Simulation Model
      </label>
      <Select
        v-model="oasisSimulationModelValue"
        :disabled="props.modelsLoading"
      >
        <option value="">Use backend default</option>
        <option v-for="m in props.models" :key="`oasis-sim-${m.id}`" :value="m.id">{{ m.name }}</option>
      </Select>
    </div>
    <div class="space-y-2">
      <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
        OASIS Report Model
      </label>
      <Select
        v-model="oasisReportModelValue"
        :disabled="props.modelsLoading"
      >
        <option value="">Use backend default</option>
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
      <Search class="w-4 h-4" />
      Run OASIS Analysis
    </Button>
    <Button
      variant="ghost"
      class="w-full"
      :loading="props.oasisPrepareLoading || (props.oasisTaskPolling && props.oasisTask?.task_type === 'oasis_prepare')"
      :disabled="!props.graphReady || !props.hasOasisAnalysis || props.oasisTaskPolling"
      @click="emit('prepare')"
    >
      <Sparkles class="w-4 h-4" />
      Prepare OASIS Package (Task)
    </Button>
    <Button
      variant="ghost"
      class="w-full"
      :loading="props.oasisTaskPolling && props.oasisTask?.task_type === 'oasis_run'"
      :disabled="!props.oasisPackage || props.oasisTaskPolling"
      @click="emit('run')"
    >
      <Network class="w-4 h-4" />
      Run OASIS Simulation (Task)
    </Button>
    <Button
      variant="ghost"
      class="w-full"
      :loading="props.oasisTaskPolling && props.oasisTask?.task_type === 'oasis_report'"
      :disabled="!props.oasisRunResult || props.oasisTaskPolling"
      @click="emit('report')"
    >
      <FileText class="w-4 h-4" />
      Generate OASIS Report (Task)
    </Button>
    <p v-if="!props.graphReady" class="text-xs text-amber-700 dark:text-amber-300">Build graph before analysis.</p>
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
      class="rounded-lg border border-stone-300/80 dark:border-zinc-700/60 bg-stone-100/75 dark:bg-zinc-800/40 p-3 text-xs text-stone-700 dark:text-zinc-200 space-y-2"
    >
      <div class="flex items-center justify-between">
        <span class="uppercase tracking-wider text-stone-500 dark:text-zinc-400">{{ props.oasisTask.task_type }}</span>
        <span class="capitalize" :class="props.oasisTaskStatusColor(props.oasisTask.status)">{{ props.oasisTask.status }}</span>
      </div>
      <p class="text-stone-700 dark:text-zinc-300">{{ props.oasisTask.message || 'Processing...' }}</p>
      <div class="h-1.5 rounded bg-stone-200/70 dark:bg-zinc-800/70 overflow-hidden">
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
      class="rounded-lg border border-stone-300/80 dark:border-zinc-700/60 bg-stone-100/75 dark:bg-zinc-800/40 p-3 text-xs text-stone-700 dark:text-zinc-300 space-y-2"
    >
      <p>Last OASIS task: {{ props.oasisTaskLastId }}</p>
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
      class="rounded-lg border border-stone-300/80 dark:border-zinc-700/60 bg-stone-100/75 dark:bg-zinc-800/40 p-3 text-sm text-stone-700 dark:text-zinc-200 whitespace-pre-wrap max-h-48 overflow-y-auto"
    >
      {{ props.graphAnalysisResult }}
    </div>
    <div
      v-if="props.hasOasisAnalysis"
      class="rounded-lg border border-emerald-300/70 bg-emerald-100 p-3 text-xs text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300"
    >
      OASIS summary ready. Guidance and agent profiles are now used by continuation generation.
    </div>
    <div
      v-if="props.oasisPackage"
      class="rounded-lg border border-amber-700/30 bg-amber-900/10 p-3 text-xs text-amber-800 dark:text-amber-200 space-y-1"
    >
      <p>Simulation Package: {{ props.oasisPackage.simulation_id }}</p>
      <p>Profiles: {{ props.oasisPackage.profiles?.length || 0 }}</p>
      <p>Events: {{ props.oasisPackage.simulation_config?.events?.length || 0 }}</p>
      <p>Platforms: {{ (props.oasisPackage.simulation_config?.active_platforms || []).join(', ') || 'N/A' }}</p>
    </div>
    <div
      v-if="props.oasisRunResult"
      class="rounded-lg border border-stone-300/80 bg-stone-100/75 p-3 text-xs text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/40 dark:text-zinc-200 space-y-1"
    >
      <p>Run: {{ props.oasisRunResult.run_id }}</p>
      <p>Rounds: {{ props.oasisRunResult.metrics?.total_rounds || 0 }}</p>
      <p>Active Agents: {{ props.oasisRunResult.metrics?.active_agents || 0 }}</p>
      <p>Estimated Posts: {{ props.oasisRunResult.metrics?.estimated_posts || 0 }}</p>
    </div>
    <div
      v-if="props.oasisReport"
      class="rounded-lg border border-amber-300/80 bg-amber-100/75 p-3 text-xs text-amber-900 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-200 space-y-1"
    >
      <p>Report: {{ props.oasisReport.report_id }}</p>
      <p class="font-medium">{{ props.oasisReport.title }}</p>
      <p class="text-amber-800 dark:text-amber-200/90 line-clamp-3">{{ props.oasisReport.executive_summary }}</p>
    </div>
  </Card>
</template>
