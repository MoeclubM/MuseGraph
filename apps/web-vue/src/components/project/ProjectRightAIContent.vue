<script setup lang="ts">
import type { Component } from 'vue'
import type { ModelInfo } from '@/api/projects'
import type {
  Operation,
  ProjectCharacter,
  ProjectGlossaryTerm,
  ProjectSearchResult,
  ProjectWorldbookEntry,
  SimulationRuntime,
} from '@/types'
import ProjectKnowledgeBasePanel from '@/components/project/ProjectKnowledgeBasePanel.vue'
import ProjectOperationPanel from '@/components/project/ProjectOperationPanel.vue'
import ProjectSimulationWorkflowCard from '@/components/project/ProjectSimulationWorkflowCard.vue'

interface OperationTypeItem {
  value: string
  label: string
  icon: Component
  description: string
}

const props = defineProps<{
  rightPanelTab: string
  projectSearchQuery: string
  projectSearchLoading: boolean
  projectSearchError: string | null
  projectSearchResults: ProjectSearchResult[]
  handleProjectSearch: () => unknown
  openProjectSearchResult: (result: ProjectSearchResult) => unknown
  selectedCharactersCount: number
  characterSelectionCountLabel: string
  charactersLoading: boolean
  projectCharacters: ProjectCharacter[]
  allCharactersSelected: boolean
  charactersError: string | null
  selectedCharacterIds: string[]
  characterFormOpen: boolean
  editingCharacterId: string
  characterForm: {
    name: string
    role: string
    profile: string
    notes: string
  }
  characterFormSubmitting: boolean
  loadCharacters: () => unknown
  beginCreateCharacter: () => unknown
  setAllCharactersSelected: (checked: boolean) => unknown
  toggleCharacterScope: (id: string, checked: boolean) => unknown
  beginEditCharacter: (character: ProjectCharacter) => unknown
  handleDeleteCharacter: (character: ProjectCharacter) => unknown
  cancelCharacterForm: () => unknown
  handleSubmitCharacter: () => unknown
  selectedGlossaryTermsCount: number
  glossarySelectionCountLabel: string
  glossaryLoading: boolean
  projectGlossaryTerms: ProjectGlossaryTerm[]
  allGlossaryTermsSelected: boolean
  glossaryError: string | null
  selectedGlossaryTermIds: string[]
  glossaryFormOpen: boolean
  editingGlossaryTermId: string
  glossaryForm: {
    term: string
    definition: string
    aliases: string
    notes: string
  }
  glossaryFormSubmitting: boolean
  loadGlossaryTerms: () => unknown
  beginCreateGlossaryTerm: () => unknown
  setAllGlossaryTermsSelected: (checked: boolean) => unknown
  toggleGlossaryScope: (id: string, checked: boolean) => unknown
  beginEditGlossaryTerm: (term: ProjectGlossaryTerm) => unknown
  handleDeleteGlossaryTerm: (term: ProjectGlossaryTerm) => unknown
  cancelGlossaryForm: () => unknown
  handleSubmitGlossaryTerm: () => unknown
  selectedWorldbookEntriesCount: number
  worldbookSelectionCountLabel: string
  worldbookLoading: boolean
  projectWorldbookEntries: ProjectWorldbookEntry[]
  allWorldbookEntriesSelected: boolean
  worldbookError: string | null
  selectedWorldbookEntryIds: string[]
  worldbookFormOpen: boolean
  editingWorldbookEntryId: string
  worldbookForm: {
    title: string
    category: string
    tags: string
    content: string
    notes: string
  }
  worldbookFormSubmitting: boolean
  loadWorldbookEntries: () => unknown
  beginCreateWorldbookEntry: () => unknown
  setAllWorldbookEntriesSelected: (checked: boolean) => unknown
  toggleWorldbookScope: (id: string, checked: boolean) => unknown
  beginEditWorldbookEntry: (entry: ProjectWorldbookEntry) => unknown
  handleDeleteWorldbookEntry: (entry: ProjectWorldbookEntry) => unknown
  cancelWorldbookForm: () => unknown
  handleSubmitWorldbookEntry: () => unknown
  operationTypes: OperationTypeItem[]
  operationType: string
  isWorkspaceEmpty: boolean
  modelsLoading: boolean
  models: ModelInfo[]
  operationModel: string
  continuationApplyMode: 'append' | 'replace' | 'new_chapter'
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
  formatDate: (dateStr: string) => string
  simulationLoading: boolean
  simulationCreating: boolean
  simulationError: string | null
  projectSimulations: SimulationRuntime[]
  confirmedSimulationId: string
  canConfirmSimulation: (sim: SimulationRuntime) => boolean
}>()

const emit = defineEmits<{
  'update:projectSearchQuery': [value: string]
  'update:operationType': [value: string]
  'update:operationModel': [value: string]
  'update:continuationApplyMode': [value: 'append' | 'replace' | 'new_chapter']
  'update:createUserPrompt': [value: string]
  'update:createOutline': [value: string]
  'update:continueUserInstruction': [value: string]
  'update:continueOutline': [value: string]
  'generate-create-outline': []
  'generate-continue-outline': []
  'run-operation': []
  'refresh-simulations': []
  'create-simulation': []
  'confirm-simulation': [simulationId: string]
  'open-simulation': [simulationId: string]
}>()
</script>

<template>
  <div v-show="rightPanelTab === 'ai'" class="space-y-5">
    <ProjectKnowledgeBasePanel
      :project-search-query="projectSearchQuery"
      :project-search-loading="projectSearchLoading"
      :project-search-error="projectSearchError"
      :project-search-results="projectSearchResults"
      :handle-project-search="handleProjectSearch"
      :open-project-search-result="openProjectSearchResult"
      :selected-characters-count="selectedCharactersCount"
      :character-selection-count-label="characterSelectionCountLabel"
      :characters-loading="charactersLoading"
      :project-characters="projectCharacters"
      :all-characters-selected="allCharactersSelected"
      :characters-error="charactersError"
      :selected-character-ids="selectedCharacterIds"
      :character-form-open="characterFormOpen"
      :editing-character-id="editingCharacterId"
      :character-form="characterForm"
      :character-form-submitting="characterFormSubmitting"
      :load-characters="loadCharacters"
      :begin-create-character="beginCreateCharacter"
      :set-all-characters-selected="setAllCharactersSelected"
      :toggle-character-scope="toggleCharacterScope"
      :begin-edit-character="beginEditCharacter"
      :handle-delete-character="handleDeleteCharacter"
      :cancel-character-form="cancelCharacterForm"
      :handle-submit-character="handleSubmitCharacter"
      :selected-glossary-terms-count="selectedGlossaryTermsCount"
      :glossary-selection-count-label="glossarySelectionCountLabel"
      :glossary-loading="glossaryLoading"
      :project-glossary-terms="projectGlossaryTerms"
      :all-glossary-terms-selected="allGlossaryTermsSelected"
      :glossary-error="glossaryError"
      :selected-glossary-term-ids="selectedGlossaryTermIds"
      :glossary-form-open="glossaryFormOpen"
      :editing-glossary-term-id="editingGlossaryTermId"
      :glossary-form="glossaryForm"
      :glossary-form-submitting="glossaryFormSubmitting"
      :load-glossary-terms="loadGlossaryTerms"
      :begin-create-glossary-term="beginCreateGlossaryTerm"
      :set-all-glossary-terms-selected="setAllGlossaryTermsSelected"
      :toggle-glossary-scope="toggleGlossaryScope"
      :begin-edit-glossary-term="beginEditGlossaryTerm"
      :handle-delete-glossary-term="handleDeleteGlossaryTerm"
      :cancel-glossary-form="cancelGlossaryForm"
      :handle-submit-glossary-term="handleSubmitGlossaryTerm"
      :selected-worldbook-entries-count="selectedWorldbookEntriesCount"
      :worldbook-selection-count-label="worldbookSelectionCountLabel"
      :worldbook-loading="worldbookLoading"
      :project-worldbook-entries="projectWorldbookEntries"
      :all-worldbook-entries-selected="allWorldbookEntriesSelected"
      :worldbook-error="worldbookError"
      :selected-worldbook-entry-ids="selectedWorldbookEntryIds"
      :worldbook-form-open="worldbookFormOpen"
      :editing-worldbook-entry-id="editingWorldbookEntryId"
      :worldbook-form="worldbookForm"
      :worldbook-form-submitting="worldbookFormSubmitting"
      :load-worldbook-entries="loadWorldbookEntries"
      :begin-create-worldbook-entry="beginCreateWorldbookEntry"
      :set-all-worldbook-entries-selected="setAllWorldbookEntriesSelected"
      :toggle-worldbook-scope="toggleWorldbookScope"
      :begin-edit-worldbook-entry="beginEditWorldbookEntry"
      :handle-delete-worldbook-entry="handleDeleteWorldbookEntry"
      :cancel-worldbook-form="cancelWorldbookForm"
      :handle-submit-worldbook-entry="handleSubmitWorldbookEntry"
      @update:project-search-query="emit('update:projectSearchQuery', $event)"
    />

    <ProjectOperationPanel
      :operation-types="operationTypes"
      :operation-type="operationType"
      :is-workspace-empty="isWorkspaceEmpty"
      :models-loading="modelsLoading"
      :models="models"
      :operation-model="operationModel"
      :continuation-apply-mode="continuationApplyMode"
      :create-user-prompt="createUserPrompt"
      :create-outline="createOutline"
      :create-outline-loading="createOutlineLoading"
      :create-outline-error="createOutlineError"
      :continue-user-instruction="continueUserInstruction"
      :continue-outline="continueOutline"
      :continue-outline-loading="continueOutlineLoading"
      :continue-outline-error="continueOutlineError"
      :graph-ready="graphReady"
      :create-prerequisites-ready="createPrerequisitesReady"
      :continue-prerequisites-ready="continuePrerequisitesReady"
      :operation-loading="operationLoading"
      :operation-primary-label="operationPrimaryLabel"
      :operation-error="operationError"
      :operation-result="operationResult"
      :operations="operations"
      :status-color="statusColor"
      :format-date="formatDate"
      @update:operation-type="emit('update:operationType', $event)"
      @update:operation-model="emit('update:operationModel', $event)"
      @update:continuation-apply-mode="emit('update:continuationApplyMode', $event)"
      @update:create-user-prompt="emit('update:createUserPrompt', $event)"
      @update:create-outline="emit('update:createOutline', $event)"
      @update:continue-user-instruction="emit('update:continueUserInstruction', $event)"
      @update:continue-outline="emit('update:continueOutline', $event)"
      @generate-create-outline="emit('generate-create-outline')"
      @generate-continue-outline="emit('generate-continue-outline')"
      @run-operation="emit('run-operation')"
    />
  </div>

  <ProjectSimulationWorkflowCard
    :visible="rightPanelTab === 'oasis'"
    :simulation-loading="simulationLoading"
    :simulation-creating="simulationCreating"
    :graph-ready="graphReady"
    :simulation-error="simulationError"
    :project-simulations="projectSimulations"
    :confirmed-simulation-id="confirmedSimulationId"
    :can-confirm-simulation="canConfirmSimulation"
    @refresh="emit('refresh-simulations')"
    @create="emit('create-simulation')"
    @confirm="emit('confirm-simulation', $event)"
    @open-simulation="emit('open-simulation', $event)"
  />
</template>
