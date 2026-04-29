import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useProjectKnowledgeBase } from '@/composables/useProjectKnowledgeBase'

vi.mock('@/api/projects', () => ({
  listProjectCharacters: vi.fn(),
  createProjectCharacter: vi.fn(),
  updateProjectCharacter: vi.fn(),
  deleteProjectCharacter: vi.fn(),
  listProjectGlossaryTerms: vi.fn(),
  createProjectGlossaryTerm: vi.fn(),
  updateProjectGlossaryTerm: vi.fn(),
  deleteProjectGlossaryTerm: vi.fn(),
  listProjectWorldbookEntries: vi.fn(),
  createProjectWorldbookEntry: vi.fn(),
  updateProjectWorldbookEntry: vi.fn(),
  deleteProjectWorldbookEntry: vi.fn(),
}))

import * as projectsApi from '@/api/projects'

const baseCharacter = {
  project_id: 'project-1',
  role: null,
  profile: null,
  notes: null,
  order_index: 0,
  created_at: '2026-03-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
}

const charA = {
  ...baseCharacter,
  id: 'char-a',
  name: 'Alpha',
}

const charB = {
  ...baseCharacter,
  id: 'char-b',
  name: 'beta',
}

function createComposable() {
  const notifySuccess = vi.fn()
  const notifyError = vi.fn()
  const parseError = vi.fn((_error: unknown, fallback: string) => `parsed:${fallback}`)

  const kb = useProjectKnowledgeBase({
    projectId: ref('project-1'),
    parseError,
    notifySuccess,
    notifyError,
  })

  return {
    kb,
    notifySuccess,
    notifyError,
    parseError,
  }
}

describe('useProjectKnowledgeBase', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads characters, sorts by name and initializes selected ids', async () => {
    vi.mocked(projectsApi.listProjectCharacters).mockResolvedValue([charB, charA])

    const { kb } = createComposable()
    await kb.loadCharacters()

    expect(projectsApi.listProjectCharacters).toHaveBeenCalledWith('project-1')
    expect(kb.projectCharacters.value.map((item) => item.id)).toEqual(['char-a', 'char-b'])
    expect(kb.selectedCharacterIds.value).toEqual(['char-a', 'char-b'])
    expect(kb.characterSelectionCountLabel.value).toBe('2/2')
    expect(kb.allCharactersSelected.value).toBe(true)
    expect(kb.charactersLoading.value).toBe(false)
    expect(kb.charactersError.value).toBeNull()
  })

  it('allows clearing all reference card selections', async () => {
    vi.mocked(projectsApi.listProjectCharacters).mockResolvedValue([charA])

    const { kb } = createComposable()
    await kb.loadCharacters()

    kb.toggleCharacterScope('char-a', false)
    expect(kb.selectedCharacterIds.value).toEqual([])
    expect(kb.allCharactersSelected.value).toBe(false)
  })

  it('validates character name before submit', async () => {
    const { kb, notifyError } = createComposable()

    kb.beginCreateCharacter()
    kb.characterForm.value.name = '   '

    await kb.handleSubmitCharacter()

    expect(projectsApi.createProjectCharacter).not.toHaveBeenCalled()
    expect(notifyError).toHaveBeenCalledWith('Character name is required')
  })

  it('creates character with normalized optional fields and resets form', async () => {
    vi.mocked(projectsApi.createProjectCharacter).mockResolvedValue(charA)
    vi.mocked(projectsApi.listProjectCharacters).mockResolvedValue([charA])

    const { kb, notifySuccess } = createComposable()

    kb.beginCreateCharacter()
    kb.characterForm.value.name = '  Lin  '
    kb.characterForm.value.role = ' '
    kb.characterForm.value.profile = ' calm and smart '
    kb.characterForm.value.notes = ''

    await kb.handleSubmitCharacter()

    expect(projectsApi.createProjectCharacter).toHaveBeenCalledWith('project-1', {
      name: 'Lin',
      role: undefined,
      profile: 'calm and smart',
      notes: undefined,
    })
    expect(notifySuccess).toHaveBeenCalledWith('Character card created')
    expect(kb.characterFormOpen.value).toBe(false)
    expect(kb.editingCharacterId.value).toBe('')
    expect(kb.characterForm.value).toEqual({
      name: '',
      role: '',
      profile: '',
      notes: '',
    })
  })

  it('creates glossary term with parsed aliases', async () => {
    const term = {
      id: 'term-1',
      project_id: 'project-1',
      term: 'RAG',
      definition: 'retrieve and generate',
      aliases: ['retrieve'],
      notes: null,
      order_index: 0,
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
    }
    vi.mocked(projectsApi.createProjectGlossaryTerm).mockResolvedValue(term)
    vi.mocked(projectsApi.listProjectGlossaryTerms).mockResolvedValue([term])

    const { kb, notifySuccess } = createComposable()

    kb.beginCreateGlossaryTerm()
    kb.glossaryForm.value.term = ' RAG '
    kb.glossaryForm.value.definition = ' '
    kb.glossaryForm.value.aliases = ' retrieval, augmented , , generation '
    kb.glossaryForm.value.notes = ''

    await kb.handleSubmitGlossaryTerm()

    expect(projectsApi.createProjectGlossaryTerm).toHaveBeenCalledWith('project-1', {
      term: 'RAG',
      definition: undefined,
      aliases: ['retrieval', 'augmented', 'generation'],
      notes: undefined,
    })
    expect(notifySuccess).toHaveBeenCalledWith('Glossary term created')
    expect(kb.glossaryFormOpen.value).toBe(false)
  })

  it('resets all knowledge base state', () => {
    const { kb } = createComposable()

    kb.projectCharacters.value = [charA]
    kb.selectedCharacterIds.value = ['char-a']
    kb.charactersError.value = 'err'
    kb.characterFormOpen.value = true
    kb.characterForm.value.name = 'temp'

    kb.projectGlossaryTerms.value = [{
      id: 'term-1',
      project_id: 'project-1',
      term: 'Term',
      definition: 'def',
      aliases: [],
      notes: null,
      order_index: 0,
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
    }]
    kb.selectedGlossaryTermIds.value = ['term-1']
    kb.glossaryError.value = 'err'
    kb.glossaryFormOpen.value = true
    kb.glossaryForm.value.term = 'temp'

    kb.projectWorldbookEntries.value = [{
      id: 'world-1',
      project_id: 'project-1',
      title: 'World',
      category: null,
      content: 'content',
      tags: [],
      notes: null,
      order_index: 0,
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
    }]
    kb.selectedWorldbookEntryIds.value = ['world-1']
    kb.worldbookError.value = 'err'
    kb.worldbookFormOpen.value = true
    kb.worldbookForm.value.title = 'temp'

    kb.resetKnowledgeBaseState()

    expect(kb.projectCharacters.value).toEqual([])
    expect(kb.selectedCharacterIds.value).toEqual([])
    expect(kb.charactersError.value).toBeNull()
    expect(kb.characterFormOpen.value).toBe(false)
    expect(kb.characterSelectionCountLabel.value).toBe('0/0')

    expect(kb.projectGlossaryTerms.value).toEqual([])
    expect(kb.selectedGlossaryTermIds.value).toEqual([])
    expect(kb.glossaryError.value).toBeNull()
    expect(kb.glossaryFormOpen.value).toBe(false)
    expect(kb.glossarySelectionCountLabel.value).toBe('0/0')

    expect(kb.projectWorldbookEntries.value).toEqual([])
    expect(kb.selectedWorldbookEntryIds.value).toEqual([])
    expect(kb.worldbookError.value).toBeNull()
    expect(kb.worldbookFormOpen.value).toBe(false)
    expect(kb.worldbookSelectionCountLabel.value).toBe('0/0')
  })
})
