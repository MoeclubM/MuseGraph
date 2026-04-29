import { describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import ProjectRightAIContent from '@/components/project/ProjectRightAIContent.vue'

const ProjectKnowledgeBasePanelStub = defineComponent({
  name: 'ProjectKnowledgeBasePanel',
  emits: ['update:project-search-query'],
  template: '<div data-test="kb-stub" />',
})

const ProjectOperationPanelStub = defineComponent({
  name: 'ProjectOperationPanel',
  emits: [
    'update:operation-type',
    'update:operation-model',
    'update:continuation-apply-mode',
    'update:create-user-prompt',
    'update:create-outline',
    'update:continue-user-instruction',
    'update:continue-outline',
    'generate-create-outline',
    'generate-continue-outline',
    'run-operation',
  ],
  template: '<div data-test="operation-stub" />',
})

const ProjectSimulationWorkflowCardStub = defineComponent({
  name: 'ProjectSimulationWorkflowCard',
  props: {
    visible: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['refresh', 'create', 'confirm', 'open-simulation'],
  template: '<div data-test="simulation-stub" />',
})

function buildBaseProps(tab: 'ai' | 'oasis' = 'ai') {
  return {
    rightPanelTab: tab,
    projectSearchQuery: '',
    projectSearchLoading: false,
    projectSearchError: null,
    projectSearchResults: [],
    handleProjectSearch: () => undefined,
    openProjectSearchResult: () => undefined,
    selectedCharactersCount: 0,
    characterSelectionCountLabel: '0/0',
    charactersLoading: false,
    projectCharacters: [],
    allCharactersSelected: false,
    charactersError: null,
    selectedCharacterIds: [],
    characterFormOpen: false,
    editingCharacterId: '',
    characterForm: { name: '', role: '', profile: '', notes: '' },
    characterFormSubmitting: false,
    loadCharacters: () => undefined,
    beginCreateCharacter: () => undefined,
    setAllCharactersSelected: () => undefined,
    toggleCharacterScope: () => undefined,
    beginEditCharacter: () => undefined,
    handleDeleteCharacter: () => undefined,
    cancelCharacterForm: () => undefined,
    handleSubmitCharacter: () => undefined,
    selectedGlossaryTermsCount: 0,
    glossarySelectionCountLabel: '0/0',
    glossaryLoading: false,
    projectGlossaryTerms: [],
    allGlossaryTermsSelected: false,
    glossaryError: null,
    selectedGlossaryTermIds: [],
    glossaryFormOpen: false,
    editingGlossaryTermId: '',
    glossaryForm: { term: '', definition: '', aliases: '', notes: '' },
    glossaryFormSubmitting: false,
    loadGlossaryTerms: () => undefined,
    beginCreateGlossaryTerm: () => undefined,
    setAllGlossaryTermsSelected: () => undefined,
    toggleGlossaryScope: () => undefined,
    beginEditGlossaryTerm: () => undefined,
    handleDeleteGlossaryTerm: () => undefined,
    cancelGlossaryForm: () => undefined,
    handleSubmitGlossaryTerm: () => undefined,
    selectedWorldbookEntriesCount: 0,
    worldbookSelectionCountLabel: '0/0',
    worldbookLoading: false,
    projectWorldbookEntries: [],
    allWorldbookEntriesSelected: false,
    worldbookError: null,
    selectedWorldbookEntryIds: [],
    worldbookFormOpen: false,
    editingWorldbookEntryId: '',
    worldbookForm: { title: '', category: '', tags: '', content: '', notes: '' },
    worldbookFormSubmitting: false,
    loadWorldbookEntries: () => undefined,
    beginCreateWorldbookEntry: () => undefined,
    setAllWorldbookEntriesSelected: () => undefined,
    toggleWorldbookScope: () => undefined,
    beginEditWorldbookEntry: () => undefined,
    handleDeleteWorldbookEntry: () => undefined,
    cancelWorldbookForm: () => undefined,
    handleSubmitWorldbookEntry: () => undefined,
    operationTypes: [],
    operationType: 'CREATE',
    isWorkspaceEmpty: false,
    modelsLoading: false,
    models: [],
    operationModel: '',
    continuationApplyMode: 'new_chapter' as const,
    createUserPrompt: '',
    createOutline: '',
    createOutlineLoading: false,
    createOutlineError: null,
    continueUserInstruction: '',
    continueOutline: '',
    continueOutlineLoading: false,
    continueOutlineError: null,
    graphReady: true,
    createPrerequisitesReady: true,
    continuePrerequisitesReady: true,
    operationLoading: false,
    operationPrimaryLabel: 'Run',
    operationError: null,
    operationResult: null,
    operations: [],
    statusColor: () => 'ok',
    formatDate: () => 'date',
    simulationLoading: false,
    simulationCreating: false,
    simulationError: null,
    projectSimulations: [],
    confirmedSimulationId: '',
    canConfirmSimulation: () => true,
  }
}

describe('ProjectRightAIContent', () => {
  it('forwards project search query updates', async () => {
    const wrapper = mount(ProjectRightAIContent, {
      props: buildBaseProps('ai') as any,
      global: {
        stubs: {
          ProjectKnowledgeBasePanel: ProjectKnowledgeBasePanelStub,
          ProjectOperationPanel: ProjectOperationPanelStub,
          ProjectSimulationWorkflowCard: ProjectSimulationWorkflowCardStub,
        },
      },
    })

    wrapper.findComponent(ProjectKnowledgeBasePanelStub).vm.$emit('update:project-search-query', 'lighthouse')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:projectSearchQuery')?.[0]).toEqual(['lighthouse'])
  })

  it('forwards operation panel events', async () => {
    const wrapper = mount(ProjectRightAIContent, {
      props: buildBaseProps('ai') as any,
      global: {
        stubs: {
          ProjectKnowledgeBasePanel: ProjectKnowledgeBasePanelStub,
          ProjectOperationPanel: ProjectOperationPanelStub,
          ProjectSimulationWorkflowCard: ProjectSimulationWorkflowCardStub,
        },
      },
    })

    const operationStub = wrapper.findComponent(ProjectOperationPanelStub)
    operationStub.vm.$emit('update:operation-model', 'gpt-4o-mini')
    operationStub.vm.$emit('generate-create-outline')
    operationStub.vm.$emit('run-operation')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:operationModel')?.[0]).toEqual(['gpt-4o-mini'])
    expect(wrapper.emitted('generate-create-outline')).toBeTruthy()
    expect(wrapper.emitted('run-operation')).toBeTruthy()
  })

  it('forwards simulation events and passes oasis visibility', async () => {
    const wrapper = mount(ProjectRightAIContent, {
      props: buildBaseProps('oasis') as any,
      global: {
        stubs: {
          ProjectKnowledgeBasePanel: ProjectKnowledgeBasePanelStub,
          ProjectOperationPanel: ProjectOperationPanelStub,
          ProjectSimulationWorkflowCard: ProjectSimulationWorkflowCardStub,
        },
      },
    })

    const simulationStub = wrapper.findComponent(ProjectSimulationWorkflowCardStub)
    expect(simulationStub.props('visible')).toBe(true)

    simulationStub.vm.$emit('refresh')
    simulationStub.vm.$emit('confirm', 'sim-123')
    simulationStub.vm.$emit('open-simulation', 'sim-123')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('refresh-simulations')).toBeTruthy()
    expect(wrapper.emitted('confirm-simulation')?.[0]).toEqual(['sim-123'])
    expect(wrapper.emitted('open-simulation')?.[0]).toEqual(['sim-123'])
  })
})
