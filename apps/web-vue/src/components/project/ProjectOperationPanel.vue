<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Sparkles } from 'lucide-vue-next'
import type { ModelInfo } from '@/api/projects'
import type { Operation } from '@/types'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Select from '@/components/ui/Select.vue'
import Textarea from '@/components/ui/Textarea.vue'

type OperationType = 'CREATE' | 'CONTINUE' | 'ANALYZE' | 'REWRITE' | 'SUMMARIZE'
type ContinuationApplyMode = 'append' | 'replace' | 'new_chapter'
type OperationTypeValue = OperationType | string

interface OperationOption {
  value: OperationTypeValue
  label: string
  icon: Component
  description: string
}

const props = defineProps<{
  operationTypes: OperationOption[]
  operationType: OperationTypeValue
  isWorkspaceEmpty: boolean
  modelsLoading: boolean
  models: ModelInfo[]
  operationModel: string
  continuationApplyMode: ContinuationApplyMode
  createUserPrompt: string
  createOutline: string
  createOutlineLoading: boolean
  createOutlineError: string | null
  continueUserInstruction: string
  continueOutline: string
  continueOutlineLoading: boolean
  continueOutlineError: string | null
  graphReady: boolean
  createPrerequisitesReady: boolean
  continuePrerequisitesReady: boolean
  operationLoading: boolean
  operationPrimaryLabel: string
  operationError: string | null
  operationResult: string | null
  operations: Operation[]
  statusColor: (status: string) => string
  formatDate: (value: string) => string
}>()

const emit = defineEmits<{
  'update:operationType': [value: OperationTypeValue]
  'update:operationModel': [value: string]
  'update:continuationApplyMode': [value: ContinuationApplyMode]
  'update:createUserPrompt': [value: string]
  'update:createOutline': [value: string]
  'update:continueUserInstruction': [value: string]
  'update:continueOutline': [value: string]
  generateCreateOutline: []
  generateContinueOutline: []
  runOperation: []
}>()

const operationModelValue = computed({
  get: () => props.operationModel,
  set: (value: string | number) => emit('update:operationModel', String(value || '')),
})

const continuationApplyModeValue = computed({
  get: () => props.continuationApplyMode,
  set: (value: string | number) => {
    const normalized = String(value || 'new_chapter')
    const allow: ContinuationApplyMode[] = ['append', 'replace', 'new_chapter']
    emit('update:continuationApplyMode', allow.includes(normalized as ContinuationApplyMode) ? normalized as ContinuationApplyMode : 'new_chapter')
  },
})

const createUserPromptValue = computed({
  get: () => props.createUserPrompt,
  set: (value: string | number) => emit('update:createUserPrompt', String(value || '')),
})

const createOutlineValue = computed({
  get: () => props.createOutline,
  set: (value: string | number) => emit('update:createOutline', String(value || '')),
})

const continueUserInstructionValue = computed({
  get: () => props.continueUserInstruction,
  set: (value: string | number) => emit('update:continueUserInstruction', String(value || '')),
})

const continueOutlineValue = computed({
  get: () => props.continueOutline,
  set: (value: string | number) => emit('update:continueOutline', String(value || '')),
})

const runDisabled = computed(() =>
  (props.operationType !== 'CREATE' && !props.graphReady)
  || props.modelsLoading
  || (props.operationType === 'CREATE' && !props.createPrerequisitesReady)
  || (props.operationType === 'CONTINUE' && !props.continuePrerequisitesReady)
)
</script>

<template>
  <div class="space-y-5">
    <div class="grid grid-cols-2 gap-2.5">
      <Button
        v-for="op in props.operationTypes"
        :key="op.value"
        variant="secondary"
        size="sm"
        class="h-auto justify-start rounded-md px-3.5 py-2.5 text-sm"
        :class="
          props.operationType === op.value
            ? 'border-amber-500 bg-amber-600/20 text-amber-700 dark:text-amber-300'
            : 'text-stone-500 dark:text-zinc-400 hover:border-stone-400 dark:hover:border-zinc-600 hover:text-stone-700 dark:hover:text-zinc-200'
        "
        :disabled="op.value === 'CREATE' && !props.isWorkspaceEmpty"
        @click="emit('update:operationType', op.value)"
      >
        <component :is="op.icon" class="w-4 h-4" />
        {{ op.label }}
      </Button>
    </div>
    <p v-if="!props.isWorkspaceEmpty" class="text-xs text-amber-700 dark:text-amber-300">
      CREATE mode is only available when workspace text length is 0.
    </p>

    <div class="space-y-2">
      <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">Operation Model</label>
      <Select
        v-model="operationModelValue"
        :disabled="props.modelsLoading"
      >
        <option value="">Auto-select first configured model</option>
        <option v-for="m in props.models" :key="m.id" :value="m.id">{{ m.name }}</option>
      </Select>
    </div>

    <div v-if="props.operationType === 'CONTINUE'" class="space-y-2">
      <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">Continuation Apply Mode</label>
      <Select
        v-model="continuationApplyModeValue"
      >
        <option value="new_chapter">Create new chapter</option>
        <option value="append">Append to editor</option>
        <option value="replace">Replace editor content</option>
      </Select>
    </div>

    <div v-if="props.operationType === 'CREATE'" class="space-y-2.5 rounded-md border border-stone-300/80 bg-stone-100/80 p-4 dark:border-zinc-700/60 dark:bg-zinc-800/45">
      <p class="text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-300">Step 0. User Prompt</p>
      <Textarea
        v-model="createUserPromptValue"
        :rows="4"
        placeholder="Describe theme, style, setting, and any must-have elements."
        class="min-h-24"
      />
      <div class="flex items-center justify-between">
        <p class="text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-300">Step A. Outline First</p>
        <Button
          variant="secondary"
          size="sm"
          :loading="props.createOutlineLoading"
          :disabled="!props.isWorkspaceEmpty || !props.createUserPrompt.trim() || props.modelsLoading"
          @click="emit('generateCreateOutline')"
        >
          Generate Outline
        </Button>
      </div>
      <Textarea
        v-model="createOutlineValue"
        :rows="8"
        placeholder="Generated outline will appear here. You can edit before drafting."
        class="min-h-44"
      />
      <p class="text-xs text-stone-600 dark:text-zinc-300/90">
        CREATE is locked to empty workspace. Outline stage uses user prompt directly (without RAG).
      </p>
      <p v-if="props.createOutlineError" class="text-xs text-red-700 dark:text-red-300">{{ props.createOutlineError }}</p>
    </div>

    <div v-if="props.operationType === 'CONTINUE'" class="space-y-2.5 rounded-md border border-stone-300/80 dark:border-zinc-700/60 bg-stone-100/75 dark:bg-zinc-800/40 p-4">
      <p class="text-xs font-medium uppercase tracking-wider text-stone-700 dark:text-zinc-300">Continue Prerequisites</p>
      <Textarea
        v-model="continueUserInstructionValue"
        :rows="4"
        placeholder="Describe what should happen next and any writing constraints."
        class="min-h-24"
      />
      <Button
        variant="secondary"
        size="sm"
        :loading="props.continueOutlineLoading"
        :disabled="!props.graphReady || !props.continueUserInstruction.trim() || props.modelsLoading"
        @click="emit('generateContinueOutline')"
      >
        1. Generate Continuation Outline
      </Button>
      <Textarea
        v-model="continueOutlineValue"
        :rows="7"
        placeholder="Continuation outline and checks from graph analysis will appear here."
        class="min-h-36"
      />
      <p v-if="props.continueOutlineError" class="text-xs text-red-700 dark:text-red-300">{{ props.continueOutlineError }}</p>
      <div class="space-y-1 text-xs">
        <p :class="props.graphReady ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">
          {{ props.graphReady ? '✓' : '•' }} RAG graph context available
        </p>
        <p :class="props.continueUserInstruction.trim() ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">
          {{ props.continueUserInstruction.trim() ? '✓' : '•' }} Continuation instruction provided
        </p>
        <p :class="props.continueOutline.trim() ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">
          {{ props.continueOutline.trim() ? '✓' : '•' }} Continuation outline generated and reviewed
        </p>
      </div>
      <p class="text-[11px] text-stone-500 dark:text-zinc-400">
        Continue mode can auto-create a new chapter from LLM output.
      </p>
    </div>

    <Alert variant="warning">
      Upload is only available in the left File Manager. Continue/analysis runs with selected chapter scope and RAG.
    </Alert>

    <Button
      variant="secondary"
      class="w-full"
      :loading="props.operationLoading"
      :disabled="runDisabled"
      @click="emit('runOperation')"
    >
      <Sparkles class="w-4 h-4" />
      {{ props.operationPrimaryLabel }}
    </Button>
    <p v-if="props.operationType !== 'CREATE' && !props.graphReady" class="text-xs text-amber-700 dark:text-amber-300">
      Build graph first. This operation requires RAG context.
    </p>

    <Alert v-if="props.operationError" variant="destructive" class="text-sm">
      {{ props.operationError }}
    </Alert>

    <div v-if="props.operationResult" class="space-y-2">
      <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">Result</h3>
      <div class="rounded-md border border-stone-300/70 dark:border-zinc-700/50 bg-stone-100/80 dark:bg-zinc-800/50 p-3 text-sm text-stone-700 dark:text-zinc-200 whitespace-pre-wrap max-h-60 overflow-y-auto">
        {{ props.operationResult }}
      </div>
    </div>

    <div v-if="props.operations.length > 0" class="space-y-2">
      <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">History</h3>
      <div class="space-y-1.5 max-h-60 overflow-y-auto">
        <div
          v-for="op in props.operations"
          :key="op.id"
          class="rounded-md border border-stone-300/70 dark:border-zinc-700/50 bg-stone-100/70 dark:bg-zinc-800/30 px-3 py-2"
        >
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-stone-700 dark:text-zinc-300">{{ op.type }}</span>
            <span :class="props.statusColor(op.status)" class="text-xs">{{ op.status }}</span>
          </div>
          <div class="mt-1 flex items-center gap-2 text-xs text-stone-500 dark:text-zinc-500">
            <span>{{ op.model }}</span>
            <span>{{ props.formatDate(op.created_at) }}</span>
          </div>
          <p v-if="op.output" class="mt-1 line-clamp-2 text-xs text-stone-500 dark:text-zinc-400">{{ op.output }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
