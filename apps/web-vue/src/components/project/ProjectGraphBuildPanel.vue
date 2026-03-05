<script setup lang="ts">
import { computed } from 'vue'
import { Network, Sparkles } from 'lucide-vue-next'
import type { ModelInfo } from '@/api/projects'
import type { ProjectOntology } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Select from '@/components/ui/Select.vue'
import Textarea from '@/components/ui/Textarea.vue'

type GraphBuildMode = 'rebuild' | 'incremental'

interface GraphBuildSummary {
  status: string
  requestedMode: string
  mode: string
  modeReason: string
  reason: string
  changedCount: number
  addedCount: number
  modifiedCount: number
  removedCount: number
}

const props = defineProps<{
  visible: boolean
  workflowSourceTextLength: number
  ontologyRequirement: string
  modelsLoading: boolean
  models: ModelInfo[]
  ontologyModel: string
  ontologyLoading: boolean
  graphCanBuild: boolean
  ontologyMessage: string
  ontologyProgress: number
  graphParsingFile: string | null
  ontologyError: string | null
  ontologyData: ProjectOntology | null
  hasOntology: boolean
  ontologyMeta: Record<string, any> | null
  graphBuildModel: string
  embeddingModels: ModelInfo[]
  graphEmbeddingModel: string
  graphRerankerModel: string
  graphBuildMode: GraphBuildMode
  graphFreshnessState: string
  graphFreshnessLabel: string
  graphFreshnessHint: string
  graphLoading: boolean
  graphBuildActionLabel: string
  graphBuildMessage: string
  graphBuildProgress: number
  graphBuildSummary: GraphBuildSummary | null
  graphError: string | null
  formatGraphBuildSummary: (summary: GraphBuildSummary | null) => string
  graphFreshnessClass: (state: string) => string
}>()

const emit = defineEmits<{
  'update:ontologyRequirement': [value: string]
  'update:ontologyModel': [value: string]
  'update:graphBuildModel': [value: string]
  'update:graphEmbeddingModel': [value: string]
  'update:graphRerankerModel': [value: string]
  'update:graphBuildMode': [value: GraphBuildMode]
  generateOntology: []
  buildGraph: []
}>()

const ontologyRequirementValue = computed({
  get: () => props.ontologyRequirement,
  set: (value: string | number) => emit('update:ontologyRequirement', String(value || '')),
})

const ontologyModelValue = computed({
  get: () => props.ontologyModel,
  set: (value: string | number) => emit('update:ontologyModel', String(value || '')),
})

const graphBuildModelValue = computed({
  get: () => props.graphBuildModel,
  set: (value: string | number) => emit('update:graphBuildModel', String(value || '')),
})

const graphEmbeddingModelValue = computed({
  get: () => props.graphEmbeddingModel,
  set: (value: string | number) => emit('update:graphEmbeddingModel', String(value || '')),
})

const graphRerankerModelValue = computed({
  get: () => props.graphRerankerModel,
  set: (value: string | number) => emit('update:graphRerankerModel', String(value || '')),
})

const graphBuildModeValue = computed({
  get: () => props.graphBuildMode,
  set: (value: string | number) => {
    const normalized = String(value || 'rebuild')
    const allow: GraphBuildMode[] = ['rebuild', 'incremental']
    emit('update:graphBuildMode', allow.includes(normalized as GraphBuildMode) ? normalized as GraphBuildMode : 'rebuild')
  },
})
</script>

<template>
  <div v-show="visible" class="space-y-5">
    <Card
      class="space-y-4 !rounded-xl !border-stone-300/80 !bg-[#f3ede1] dark:!border-zinc-700/60 dark:!bg-zinc-800/55 !p-5"
    >
      <div class="space-y-2">
        <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
          Step 1. Ontology Generation
        </h3>
        <div class="rounded-lg border border-amber-700/30 bg-amber-900/10 p-3 space-y-1.5">
          <p class="text-sm font-medium text-amber-800 dark:text-amber-200">
            用途：先定义实体/关系本体，作为 RAG 检索与图谱入库的结构约束。
          </p>
          <p class="text-xs text-amber-700 dark:text-amber-300/90">
            未完成本体生成时，Step 2 图谱构建不可执行，AI 创作与 OASIS 模拟也会缺少可靠上下文。
          </p>
          <p class="text-xs text-amber-700 dark:text-amber-300/80">
            数据源始终来自左侧已选章节，当前文本长度：{{ props.workflowSourceTextLength.toLocaleString() }} characters
          </p>
        </div>
      </div>

      <div class="space-y-2.5">
        <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
          Requirement Preset
        </label>
        <Textarea
          v-model="ontologyRequirementValue"
          :rows="5"
          placeholder="Edit ontology requirement preset"
          class="min-h-28"
        />
        <p class="text-[11px] text-stone-500 dark:text-zinc-500">
          Preset prompt is enabled by default. You can edit it before each generation.
        </p>
      </div>

      <div class="space-y-2">
        <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
          Ontology Model
        </label>
        <Select
          v-model="ontologyModelValue"
          :disabled="props.modelsLoading"
        >
          <option value="">Use backend default</option>
          <option v-for="m in props.models" :key="`ontology-${m.id}`" :value="m.id">{{ m.name }}</option>
        </Select>
      </div>

      <Button
        variant="secondary"
        class="w-full"
        :loading="props.ontologyLoading"
        :disabled="!props.graphCanBuild"
        @click="emit('generateOntology')"
      >
        <Sparkles class="w-4 h-4" />
        Generate Ontology
      </Button>

      <div v-if="props.ontologyLoading || props.ontologyMessage" class="space-y-1">
        <div class="flex items-center justify-between text-xs text-stone-500 dark:text-zinc-400">
          <span>{{ props.ontologyMessage || 'Processing...' }}</span>
          <span>{{ props.ontologyProgress }}%</span>
        </div>
        <div class="h-1.5 rounded bg-stone-200/70 dark:bg-zinc-800/70 overflow-hidden">
          <div
            class="h-full bg-amber-500 transition-all duration-300"
            :style="{ width: `${props.ontologyProgress}%` }"
          />
        </div>
        <p v-if="props.graphParsingFile" class="text-xs text-stone-500 dark:text-zinc-500 truncate">
          Parsing: {{ props.graphParsingFile }}
        </p>
      </div>

      <Alert v-if="props.ontologyError" variant="destructive" class="text-sm">
        {{ props.ontologyError }}
      </Alert>

      <Alert
        v-if="props.ontologyData && !props.hasOntology && !props.ontologyLoading"
        variant="destructive"
        class="text-sm"
      >
        Current ontology is invalid for graph build. Regenerate ontology until valid structured output is returned.
      </Alert>

      <div v-if="props.hasOntology" class="rounded-lg border border-emerald-700/40 bg-emerald-900/10 p-3 space-y-2">
        <div class="flex items-center justify-between text-xs text-emerald-700 dark:text-emerald-300">
          <span>Ontology ready</span>
          <span>{{ props.ontologyData?.entity_types?.length || 0 }} entities / {{ props.ontologyData?.edge_types?.length || 0 }} relations</span>
        </div>
        <div class="space-y-1 text-[11px] text-stone-600 dark:text-zinc-300">
          <p v-if="props.ontologyMeta?.model">
            Model:
            <span class="font-medium">{{ props.ontologyMeta.model }}</span>
            <span v-if="props.ontologyMeta?.provider"> · {{ props.ontologyMeta.provider }}</span>
          </p>
          <p v-if="props.ontologyMeta?.api_called">
            Tokens: {{ props.ontologyMeta?.input_tokens || 0 }} in / {{ props.ontologyMeta?.output_tokens || 0 }} out
          </p>
        </div>
        <div class="flex flex-wrap gap-1">
          <span
            v-for="entity in (props.ontologyData?.entity_types || []).slice(0, 8)"
            :key="entity.name"
            class="rounded-full bg-stone-200/80 dark:bg-zinc-800/80 px-2 py-0.5 text-xs text-stone-700 dark:text-zinc-300"
          >
            {{ entity.name }}
          </span>
        </div>
      </div>
    </Card>

    <Card
      class="space-y-4 !rounded-xl !border-stone-300/80 !bg-[#f3ede1] dark:!border-zinc-700/60 dark:!bg-zinc-800/55 !p-5"
    >
      <div class="space-y-2.5">
        <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
          Step 2. Graph Build
        </h3>
        <div class="space-y-2">
          <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
            Graph Build Model
          </label>
          <Select
            v-model="graphBuildModelValue"
            :disabled="props.modelsLoading"
          >
            <option value="">Use backend default</option>
            <option v-for="m in props.models" :key="`graph-build-${m.id}`" :value="m.id">{{ m.name }}</option>
          </Select>
        </div>
        <div class="space-y-2">
          <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
            Embedding Model
          </label>
          <Select
            v-model="graphEmbeddingModelValue"
            :disabled="props.modelsLoading"
          >
            <option value="">Use backend auto select</option>
            <option
              v-for="m in props.embeddingModels"
              :key="`graph-embed-${m.id}`"
              :value="m.id"
            >
              {{ m.name }}
            </option>
          </Select>
        </div>
        <div class="space-y-2">
          <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
            Workspace Reranker Model (RAG)
          </label>
          <Select
            v-model="graphRerankerModelValue"
            :disabled="props.modelsLoading"
          >
            <option value="">Disabled</option>
            <option v-for="m in props.models" :key="`graph-reranker-${m.id}`" :value="m.id">{{ m.name }}</option>
          </Select>
          <p class="text-[11px] text-stone-500 dark:text-zinc-500">
            Stored per workspace and used by RAG retrieval in graph search and AI operations.
          </p>
        </div>
        <div class="space-y-2">
          <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
            Build Mode
          </label>
          <Select v-model="graphBuildModeValue">
            <option value="rebuild">From Zero (Clear Old Graph)</option>
            <option value="incremental">Incremental Update (Changed Chapters Only)</option>
          </Select>
          <p class="text-[11px] text-stone-500 dark:text-zinc-500">
            Rebuild ensures a clean graph. Incremental mode appends only changed chapter content.
          </p>
        </div>
        <div
          class="rounded-lg border px-3 py-2 text-[11px]"
          :class="props.graphFreshnessClass(props.graphFreshnessState)"
        >
          <p class="font-medium">
            {{ props.graphFreshnessLabel }}
          </p>
          <p
            v-if="props.graphFreshnessHint"
            class="mt-0.5 opacity-90"
          >
            {{ props.graphFreshnessHint }}
          </p>
        </div>
        <Button
          variant="primary"
          class="w-full"
          :loading="props.graphLoading"
          :disabled="!props.graphCanBuild || !props.hasOntology"
          @click="emit('buildGraph')"
        >
          <Network class="w-4 h-4" />
          {{ props.graphBuildActionLabel }}
        </Button>
      </div>

      <div v-if="props.graphLoading || props.graphBuildMessage" class="space-y-1">
        <div class="flex items-center justify-between text-xs text-stone-500 dark:text-zinc-400">
          <span>{{ props.graphBuildMessage || 'Processing...' }}</span>
          <span>{{ props.graphBuildProgress }}%</span>
        </div>
        <div class="h-1.5 rounded bg-stone-200/70 dark:bg-zinc-800/70 overflow-hidden">
          <div
            class="h-full bg-amber-500 transition-all duration-300"
            :style="{ width: `${props.graphBuildProgress}%` }"
          />
        </div>
        <p v-if="props.graphParsingFile" class="text-xs text-stone-500 dark:text-zinc-500 truncate">
          Parsing: {{ props.graphParsingFile }}
        </p>
      </div>
      <div
        v-if="props.graphBuildSummary"
        class="rounded-lg border border-stone-300/80 bg-stone-100/70 px-3 py-2 text-[11px] text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/45 dark:text-zinc-300 space-y-1"
      >
        <p>
          Last graph build:
          {{ props.formatGraphBuildSummary(props.graphBuildSummary) || '-' }}
        </p>
        <p v-if="props.graphBuildSummary.modeReason" class="text-stone-600 dark:text-zinc-400">
          Mode reason: {{ props.graphBuildSummary.modeReason }}
        </p>
        <p v-if="props.graphBuildSummary.reason" class="text-stone-600 dark:text-zinc-400">
          Detail: {{ props.graphBuildSummary.reason }}
        </p>
      </div>

      <p v-if="!props.hasOntology" class="text-xs text-amber-700 dark:text-amber-300">
        Please complete Step 1 first.
      </p>

      <Alert v-if="props.graphError" variant="destructive" class="text-sm">
        {{ props.graphError }}
      </Alert>
    </Card>
  </div>
</template>
