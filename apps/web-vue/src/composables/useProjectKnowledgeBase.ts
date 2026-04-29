import { computed, ref, type Ref } from 'vue'
import {
  listProjectCharacters,
  createProjectCharacter,
  updateProjectCharacter,
  deleteProjectCharacter,
  listProjectGlossaryTerms,
  createProjectGlossaryTerm,
  updateProjectGlossaryTerm,
  deleteProjectGlossaryTerm,
  listProjectWorldbookEntries,
  createProjectWorldbookEntry,
  updateProjectWorldbookEntry,
  deleteProjectWorldbookEntry,
} from '@/api/projects'
import type {
  ProjectCharacter,
  ProjectGlossaryTerm,
  ProjectWorldbookEntry,
} from '@/types'

type ParseError = (error: unknown, fallback: string) => string

type Notify = (message: string) => void

interface UseProjectKnowledgeBaseOptions {
  projectId: Ref<string>
  parseError: ParseError
  notifySuccess?: Notify
  notifyError?: Notify
}

export function useProjectKnowledgeBase(options: UseProjectKnowledgeBaseOptions) {
  const {
    projectId,
    parseError,
    notifySuccess,
    notifyError,
  } = options

  const projectCharacters = ref<ProjectCharacter[]>([])
  const selectedCharacterIds = ref<string[]>([])
  const charactersLoading = ref(false)
  const charactersError = ref<string | null>(null)
  const characterFormOpen = ref(false)
  const characterFormSubmitting = ref(false)
  const editingCharacterId = ref<string>('')
  const characterForm = ref({
    name: '',
    role: '',
    profile: '',
    notes: '',
  })
  const characterSelectionInitialized = ref(false)

  const projectGlossaryTerms = ref<ProjectGlossaryTerm[]>([])
  const selectedGlossaryTermIds = ref<string[]>([])
  const glossaryLoading = ref(false)
  const glossaryError = ref<string | null>(null)
  const glossaryFormOpen = ref(false)
  const glossaryFormSubmitting = ref(false)
  const editingGlossaryTermId = ref<string>('')
  const glossaryForm = ref({
    term: '',
    definition: '',
    aliases: '',
    notes: '',
  })
  const glossarySelectionInitialized = ref(false)

  const projectWorldbookEntries = ref<ProjectWorldbookEntry[]>([])
  const selectedWorldbookEntryIds = ref<string[]>([])
  const worldbookLoading = ref(false)
  const worldbookError = ref<string | null>(null)
  const worldbookFormOpen = ref(false)
  const worldbookFormSubmitting = ref(false)
  const editingWorldbookEntryId = ref<string>('')
  const worldbookForm = ref({
    title: '',
    category: '',
    tags: '',
    content: '',
    notes: '',
  })
  const worldbookSelectionInitialized = ref(false)

  function normalizeOptionalText(value: string): string | undefined {
    const normalized = value.trim()
    return normalized || undefined
  }

  const selectedCharacters = computed(() => {
    const selectedSet = new Set(selectedCharacterIds.value)
    return projectCharacters.value.filter((character) => selectedSet.has(character.id))
  })

  const selectedGlossaryTerms = computed(() => {
    const selectedSet = new Set(selectedGlossaryTermIds.value)
    return projectGlossaryTerms.value.filter((item) => selectedSet.has(item.id))
  })

  const selectedWorldbookEntries = computed(() => {
    const selectedSet = new Set(selectedWorldbookEntryIds.value)
    return projectWorldbookEntries.value.filter((item) => selectedSet.has(item.id))
  })

  const allCharactersSelected = computed(() =>
    projectCharacters.value.length > 0
    && selectedCharacterIds.value.length === projectCharacters.value.length
  )

  const allGlossaryTermsSelected = computed(() =>
    projectGlossaryTerms.value.length > 0
    && selectedGlossaryTermIds.value.length === projectGlossaryTerms.value.length
  )

  const allWorldbookEntriesSelected = computed(() =>
    projectWorldbookEntries.value.length > 0
    && selectedWorldbookEntryIds.value.length === projectWorldbookEntries.value.length
  )

  const characterSelectionCountLabel = computed(() => {
    const selected = selectedCharacterIds.value.length
    const total = projectCharacters.value.length
    return `${selected}/${total}`
  })

  const glossarySelectionCountLabel = computed(() => {
    const selected = selectedGlossaryTermIds.value.length
    const total = projectGlossaryTerms.value.length
    return `${selected}/${total}`
  })

  const worldbookSelectionCountLabel = computed(() => {
    const selected = selectedWorldbookEntryIds.value.length
    const total = projectWorldbookEntries.value.length
    return `${selected}/${total}`
  })

  function sortCharacters(list: ProjectCharacter[]): ProjectCharacter[] {
    return [...list].sort((a, b) => {
      const aName = String(a.name || '').trim().toLowerCase()
      const bName = String(b.name || '').trim().toLowerCase()
      return aName.localeCompare(bName)
    })
  }

  function syncSelectedCharacterIds(nextCharacters: ProjectCharacter[]) {
    const validIds = new Set(nextCharacters.map((item) => item.id))
    const current = selectedCharacterIds.value.filter((id) => validIds.has(id))

    if (!characterSelectionInitialized.value) {
      selectedCharacterIds.value = nextCharacters.map((item) => item.id)
      characterSelectionInitialized.value = true
      return
    }

    if (!current.length && nextCharacters.length && !selectedCharacterIds.value.length) {
      selectedCharacterIds.value = nextCharacters.map((item) => item.id)
      return
    }

    selectedCharacterIds.value = current
  }

  function resetCharacterForm() {
    editingCharacterId.value = ''
    characterForm.value = {
      name: '',
      role: '',
      profile: '',
      notes: '',
    }
    characterFormOpen.value = false
    characterFormSubmitting.value = false
  }

  function beginCreateCharacter() {
    resetCharacterForm()
    characterFormOpen.value = true
  }

  function beginEditCharacter(character: ProjectCharacter) {
    editingCharacterId.value = character.id
    characterForm.value = {
      name: character.name || '',
      role: character.role || '',
      profile: character.profile || '',
      notes: character.notes || '',
    }
    characterFormOpen.value = true
  }

  function cancelCharacterForm() {
    resetCharacterForm()
  }

  async function loadCharacters(silent = false) {
    if (!silent) charactersLoading.value = true
    charactersError.value = null
    try {
      const rows = await listProjectCharacters(projectId.value)
      const ordered = sortCharacters(rows || [])
      projectCharacters.value = ordered
      syncSelectedCharacterIds(ordered)
    } catch (error: unknown) {
      const message = parseError(error, 'Failed to load character cards')
      charactersError.value = message
      if (!silent) notifyError?.(message)
    } finally {
      if (!silent) charactersLoading.value = false
    }
  }

  async function handleSubmitCharacter() {
    const name = characterForm.value.name.trim()
    if (!name) {
      notifyError?.('Character name is required')
      return
    }

    characterFormSubmitting.value = true
    try {
      const payload = {
        name,
        role: normalizeOptionalText(characterForm.value.role),
        profile: normalizeOptionalText(characterForm.value.profile),
        notes: normalizeOptionalText(characterForm.value.notes),
      }

      if (editingCharacterId.value) {
        await updateProjectCharacter(projectId.value, editingCharacterId.value, payload)
        notifySuccess?.('Character card updated')
      } else {
        await createProjectCharacter(projectId.value, payload)
        notifySuccess?.('Character card created')
      }

      await loadCharacters(true)
      resetCharacterForm()
    } catch (error: unknown) {
      notifyError?.(parseError(error, 'Failed to save character card'))
    } finally {
      characterFormSubmitting.value = false
    }
  }

  async function handleDeleteCharacter(character: ProjectCharacter) {
    if (!window.confirm(`Delete character card "${character.name || 'Untitled'}"?`)) return
    try {
      await deleteProjectCharacter(projectId.value, character.id)
      notifySuccess?.('Character card deleted')
      await loadCharacters(true)
    } catch (error: unknown) {
      notifyError?.(parseError(error, 'Failed to delete character card'))
    }
  }

  function toggleCharacterScope(characterId: string, checked: boolean) {
    const current = new Set(selectedCharacterIds.value)
    if (checked) current.add(characterId)
    else current.delete(characterId)
    selectedCharacterIds.value = Array.from(current)
  }

  function setAllCharactersSelected(checked: boolean) {
    selectedCharacterIds.value = checked
      ? projectCharacters.value.map((item) => item.id)
      : []
  }

  function parseListInput(input: string): string[] {
    return input
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
  }

  function sortGlossaryTerms(list: ProjectGlossaryTerm[]): ProjectGlossaryTerm[] {
    return [...list].sort((a, b) => {
      const aTerm = String(a.term || '').trim().toLowerCase()
      const bTerm = String(b.term || '').trim().toLowerCase()
      return aTerm.localeCompare(bTerm)
    })
  }

  function syncSelectedGlossaryTermIds(nextTerms: ProjectGlossaryTerm[]) {
    const validIds = new Set(nextTerms.map((item) => item.id))
    const current = selectedGlossaryTermIds.value.filter((id) => validIds.has(id))

    if (!glossarySelectionInitialized.value) {
      selectedGlossaryTermIds.value = nextTerms.map((item) => item.id)
      glossarySelectionInitialized.value = true
      return
    }

    if (!current.length && nextTerms.length && !selectedGlossaryTermIds.value.length) {
      selectedGlossaryTermIds.value = nextTerms.map((item) => item.id)
      return
    }

    selectedGlossaryTermIds.value = current
  }

  function resetGlossaryForm() {
    editingGlossaryTermId.value = ''
    glossaryForm.value = {
      term: '',
      definition: '',
      aliases: '',
      notes: '',
    }
    glossaryFormOpen.value = false
    glossaryFormSubmitting.value = false
  }

  function beginCreateGlossaryTerm() {
    resetGlossaryForm()
    glossaryFormOpen.value = true
  }

  function beginEditGlossaryTerm(term: ProjectGlossaryTerm) {
    editingGlossaryTermId.value = term.id
    glossaryForm.value = {
      term: term.term || '',
      definition: term.definition || '',
      aliases: (term.aliases || []).join(', '),
      notes: term.notes || '',
    }
    glossaryFormOpen.value = true
  }

  function cancelGlossaryForm() {
    resetGlossaryForm()
  }

  async function loadGlossaryTerms(silent = false) {
    if (!silent) glossaryLoading.value = true
    glossaryError.value = null
    try {
      const rows = await listProjectGlossaryTerms(projectId.value)
      const ordered = sortGlossaryTerms(rows || [])
      projectGlossaryTerms.value = ordered
      syncSelectedGlossaryTermIds(ordered)
    } catch (error: unknown) {
      const message = parseError(error, 'Failed to load glossary terms')
      glossaryError.value = message
      if (!silent) notifyError?.(message)
    } finally {
      if (!silent) glossaryLoading.value = false
    }
  }

  async function handleSubmitGlossaryTerm() {
    const term = glossaryForm.value.term.trim()
    if (!term) {
      notifyError?.('Glossary term is required')
      return
    }

    glossaryFormSubmitting.value = true
    try {
      const aliases = parseListInput(glossaryForm.value.aliases)
      const payload = {
        term,
        definition: normalizeOptionalText(glossaryForm.value.definition),
        aliases,
        notes: normalizeOptionalText(glossaryForm.value.notes),
      }

      if (editingGlossaryTermId.value) {
        await updateProjectGlossaryTerm(projectId.value, editingGlossaryTermId.value, payload)
        notifySuccess?.('Glossary term updated')
      } else {
        await createProjectGlossaryTerm(projectId.value, payload)
        notifySuccess?.('Glossary term created')
      }

      await loadGlossaryTerms(true)
      resetGlossaryForm()
    } catch (error: unknown) {
      notifyError?.(parseError(error, 'Failed to save glossary term'))
    } finally {
      glossaryFormSubmitting.value = false
    }
  }

  async function handleDeleteGlossaryTerm(term: ProjectGlossaryTerm) {
    if (!window.confirm(`Delete glossary term "${term.term || 'Untitled'}"?`)) return
    try {
      await deleteProjectGlossaryTerm(projectId.value, term.id)
      notifySuccess?.('Glossary term deleted')
      await loadGlossaryTerms(true)
    } catch (error: unknown) {
      notifyError?.(parseError(error, 'Failed to delete glossary term'))
    }
  }

  function toggleGlossaryScope(termId: string, checked: boolean) {
    const current = new Set(selectedGlossaryTermIds.value)
    if (checked) current.add(termId)
    else current.delete(termId)
    selectedGlossaryTermIds.value = Array.from(current)
  }

  function setAllGlossaryTermsSelected(checked: boolean) {
    selectedGlossaryTermIds.value = checked
      ? projectGlossaryTerms.value.map((item) => item.id)
      : []
  }

  function sortWorldbookEntries(list: ProjectWorldbookEntry[]): ProjectWorldbookEntry[] {
    return [...list].sort((a, b) => {
      const aTitle = String(a.title || '').trim().toLowerCase()
      const bTitle = String(b.title || '').trim().toLowerCase()
      return aTitle.localeCompare(bTitle)
    })
  }

  function syncSelectedWorldbookEntryIds(nextEntries: ProjectWorldbookEntry[]) {
    const validIds = new Set(nextEntries.map((item) => item.id))
    const current = selectedWorldbookEntryIds.value.filter((id) => validIds.has(id))

    if (!worldbookSelectionInitialized.value) {
      selectedWorldbookEntryIds.value = nextEntries.map((item) => item.id)
      worldbookSelectionInitialized.value = true
      return
    }

    if (!current.length && nextEntries.length && !selectedWorldbookEntryIds.value.length) {
      selectedWorldbookEntryIds.value = nextEntries.map((item) => item.id)
      return
    }

    selectedWorldbookEntryIds.value = current
  }

  function resetWorldbookForm() {
    editingWorldbookEntryId.value = ''
    worldbookForm.value = {
      title: '',
      category: '',
      tags: '',
      content: '',
      notes: '',
    }
    worldbookFormOpen.value = false
    worldbookFormSubmitting.value = false
  }

  function beginCreateWorldbookEntry() {
    resetWorldbookForm()
    worldbookFormOpen.value = true
  }

  function beginEditWorldbookEntry(entry: ProjectWorldbookEntry) {
    editingWorldbookEntryId.value = entry.id
    worldbookForm.value = {
      title: entry.title || '',
      category: entry.category || '',
      tags: (entry.tags || []).join(', '),
      content: entry.content || '',
      notes: entry.notes || '',
    }
    worldbookFormOpen.value = true
  }

  function cancelWorldbookForm() {
    resetWorldbookForm()
  }

  async function loadWorldbookEntries(silent = false) {
    if (!silent) worldbookLoading.value = true
    worldbookError.value = null
    try {
      const rows = await listProjectWorldbookEntries(projectId.value)
      const ordered = sortWorldbookEntries(rows || [])
      projectWorldbookEntries.value = ordered
      syncSelectedWorldbookEntryIds(ordered)
    } catch (error: unknown) {
      const message = parseError(error, 'Failed to load worldbook entries')
      worldbookError.value = message
      if (!silent) notifyError?.(message)
    } finally {
      if (!silent) worldbookLoading.value = false
    }
  }

  async function handleSubmitWorldbookEntry() {
    const title = worldbookForm.value.title.trim()
    if (!title) {
      notifyError?.('Worldbook title is required')
      return
    }

    worldbookFormSubmitting.value = true
    try {
      const tags = parseListInput(worldbookForm.value.tags)
      const payload = {
        title,
        category: normalizeOptionalText(worldbookForm.value.category),
        tags,
        content: normalizeOptionalText(worldbookForm.value.content),
        notes: normalizeOptionalText(worldbookForm.value.notes),
      }

      if (editingWorldbookEntryId.value) {
        await updateProjectWorldbookEntry(projectId.value, editingWorldbookEntryId.value, payload)
        notifySuccess?.('Worldbook entry updated')
      } else {
        await createProjectWorldbookEntry(projectId.value, payload)
        notifySuccess?.('Worldbook entry created')
      }

      await loadWorldbookEntries(true)
      resetWorldbookForm()
    } catch (error: unknown) {
      notifyError?.(parseError(error, 'Failed to save worldbook entry'))
    } finally {
      worldbookFormSubmitting.value = false
    }
  }

  async function handleDeleteWorldbookEntry(entry: ProjectWorldbookEntry) {
    if (!window.confirm(`Delete worldbook entry "${entry.title || 'Untitled'}"?`)) return
    try {
      await deleteProjectWorldbookEntry(projectId.value, entry.id)
      notifySuccess?.('Worldbook entry deleted')
      await loadWorldbookEntries(true)
    } catch (error: unknown) {
      notifyError?.(parseError(error, 'Failed to delete worldbook entry'))
    }
  }

  function toggleWorldbookScope(entryId: string, checked: boolean) {
    const current = new Set(selectedWorldbookEntryIds.value)
    if (checked) current.add(entryId)
    else current.delete(entryId)
    selectedWorldbookEntryIds.value = Array.from(current)
  }

  function setAllWorldbookEntriesSelected(checked: boolean) {
    selectedWorldbookEntryIds.value = checked
      ? projectWorldbookEntries.value.map((item) => item.id)
      : []
  }

  function resetKnowledgeBaseState() {
    projectCharacters.value = []
    selectedCharacterIds.value = []
    characterSelectionInitialized.value = false
    charactersLoading.value = false
    charactersError.value = null
    characterFormOpen.value = false
    characterFormSubmitting.value = false
    resetCharacterForm()

    projectGlossaryTerms.value = []
    selectedGlossaryTermIds.value = []
    glossarySelectionInitialized.value = false
    glossaryLoading.value = false
    glossaryError.value = null
    glossaryFormOpen.value = false
    glossaryFormSubmitting.value = false
    resetGlossaryForm()

    projectWorldbookEntries.value = []
    selectedWorldbookEntryIds.value = []
    worldbookSelectionInitialized.value = false
    worldbookLoading.value = false
    worldbookError.value = null
    worldbookFormOpen.value = false
    worldbookFormSubmitting.value = false
    resetWorldbookForm()
  }

  return {
    projectCharacters,
    selectedCharacterIds,
    charactersLoading,
    charactersError,
    characterFormOpen,
    characterFormSubmitting,
    editingCharacterId,
    characterForm,
    selectedCharacters,
    allCharactersSelected,
    characterSelectionCountLabel,
    loadCharacters,
    beginCreateCharacter,
    beginEditCharacter,
    cancelCharacterForm,
    handleSubmitCharacter,
    handleDeleteCharacter,
    toggleCharacterScope,
    setAllCharactersSelected,
    resetCharacterForm,
    projectGlossaryTerms,
    selectedGlossaryTermIds,
    glossaryLoading,
    glossaryError,
    glossaryFormOpen,
    glossaryFormSubmitting,
    editingGlossaryTermId,
    glossaryForm,
    selectedGlossaryTerms,
    allGlossaryTermsSelected,
    glossarySelectionCountLabel,
    loadGlossaryTerms,
    beginCreateGlossaryTerm,
    beginEditGlossaryTerm,
    cancelGlossaryForm,
    handleSubmitGlossaryTerm,
    handleDeleteGlossaryTerm,
    toggleGlossaryScope,
    setAllGlossaryTermsSelected,
    resetGlossaryForm,
    projectWorldbookEntries,
    selectedWorldbookEntryIds,
    worldbookLoading,
    worldbookError,
    worldbookFormOpen,
    worldbookFormSubmitting,
    editingWorldbookEntryId,
    worldbookForm,
    selectedWorldbookEntries,
    allWorldbookEntriesSelected,
    worldbookSelectionCountLabel,
    loadWorldbookEntries,
    beginCreateWorldbookEntry,
    beginEditWorldbookEntry,
    cancelWorldbookForm,
    handleSubmitWorldbookEntry,
    handleDeleteWorldbookEntry,
    toggleWorldbookScope,
    setAllWorldbookEntriesSelected,
    resetWorldbookForm,
    resetKnowledgeBaseState,
  }
}
