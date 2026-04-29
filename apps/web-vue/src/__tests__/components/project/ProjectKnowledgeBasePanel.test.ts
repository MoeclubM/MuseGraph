import { describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import ProjectKnowledgeBasePanel from '@/components/project/ProjectKnowledgeBasePanel.vue'

const ButtonStub = defineComponent({
  name: 'Button',
  props: {
    disabled: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['click'],
  template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
})

const InputStub = defineComponent({
  name: 'Input',
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
  },
  emits: ['update:modelValue', 'keydown'],
  template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @keydown="$emit(\'keydown\', $event)" />',
})

const CheckboxStub = defineComponent({
  name: 'Checkbox',
  template: '<input type="checkbox" />',
})

const AlertStub = defineComponent({
  name: 'Alert',
  template: '<div><slot /></div>',
})

const TextareaStub = defineComponent({
  name: 'Textarea',
  template: '<textarea />',
})

function buildProps() {
  return {
    projectSearchQuery: 'lighthouse',
    projectSearchLoading: false,
    projectSearchError: null,
    projectSearchResults: [
      {
        item_type: 'chapter',
        item_id: 'ch-1',
        title: 'Opening',
        matched_field: 'content',
        snippet: 'The lighthouse hides a signal key.',
        order_index: 0,
      },
    ],
    handleProjectSearch: vi.fn(),
    openProjectSearchResult: vi.fn(),
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
    loadCharacters: vi.fn(),
    beginCreateCharacter: vi.fn(),
    setAllCharactersSelected: vi.fn(),
    toggleCharacterScope: vi.fn(),
    beginEditCharacter: vi.fn(),
    handleDeleteCharacter: vi.fn(),
    cancelCharacterForm: vi.fn(),
    handleSubmitCharacter: vi.fn(),
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
    loadGlossaryTerms: vi.fn(),
    beginCreateGlossaryTerm: vi.fn(),
    setAllGlossaryTermsSelected: vi.fn(),
    toggleGlossaryScope: vi.fn(),
    beginEditGlossaryTerm: vi.fn(),
    handleDeleteGlossaryTerm: vi.fn(),
    cancelGlossaryForm: vi.fn(),
    handleSubmitGlossaryTerm: vi.fn(),
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
    loadWorldbookEntries: vi.fn(),
    beginCreateWorldbookEntry: vi.fn(),
    setAllWorldbookEntriesSelected: vi.fn(),
    toggleWorldbookScope: vi.fn(),
    beginEditWorldbookEntry: vi.fn(),
    handleDeleteWorldbookEntry: vi.fn(),
    cancelWorldbookForm: vi.fn(),
    handleSubmitWorldbookEntry: vi.fn(),
  }
}

describe('ProjectKnowledgeBasePanel', () => {
  it('renders project search results and opens selected result', async () => {
    const props = buildProps()
    const wrapper = mount(ProjectKnowledgeBasePanel, {
      props: props as any,
      global: {
        stubs: {
          Alert: AlertStub,
          Button: ButtonStub,
          Checkbox: CheckboxStub,
          Input: InputStub,
          Textarea: TextareaStub,
        },
      },
    })

    expect(wrapper.text()).toContain('Project Search')
    expect(wrapper.text()).toContain('Opening')
    expect(wrapper.text()).toContain('The lighthouse hides a signal key.')

    await wrapper.findAll('button').find((button) => button.text().includes('Opening'))!.trigger('click')
    expect(props.openProjectSearchResult).toHaveBeenCalledWith(props.projectSearchResults[0])
  })

  it('emits query updates and triggers search', async () => {
    const props = buildProps()
    const wrapper = mount(ProjectKnowledgeBasePanel, {
      props: props as any,
      global: {
        stubs: {
          Alert: AlertStub,
          Button: ButtonStub,
          Checkbox: CheckboxStub,
          Input: InputStub,
          Textarea: TextareaStub,
        },
      },
    })

    wrapper.findComponent(InputStub).vm.$emit('update:modelValue', 'beacon')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:projectSearchQuery')?.[0]).toEqual(['beacon'])

    await wrapper.findAll('button').find((button) => button.text() === 'Search')!.trigger('click')
    expect(props.handleProjectSearch).toHaveBeenCalled()
  })
})
