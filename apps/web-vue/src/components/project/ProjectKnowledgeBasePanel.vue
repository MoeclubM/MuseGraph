<script setup lang="ts">
import type {
  ProjectCharacter,
  ProjectGlossaryTerm,
  ProjectSearchResult,
  ProjectWorldbookEntry,
} from '@/types'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Input from '@/components/ui/Input.vue'
import Textarea from '@/components/ui/Textarea.vue'

type CharacterForm = {
  name: string
  role: string
  profile: string
  notes: string
}

type GlossaryForm = {
  term: string
  definition: string
  aliases: string
  notes: string
}

type WorldbookForm = {
  title: string
  category: string
  tags: string
  content: string
  notes: string
}

const props = defineProps<{
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
  characterForm: CharacterForm
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
  glossaryForm: GlossaryForm
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
  worldbookForm: WorldbookForm
  worldbookFormSubmitting: boolean
  loadWorldbookEntries: () => unknown
  beginCreateWorldbookEntry: () => unknown
  setAllWorldbookEntriesSelected: (checked: boolean) => unknown
  toggleWorldbookScope: (id: string, checked: boolean) => unknown
  beginEditWorldbookEntry: (entry: ProjectWorldbookEntry) => unknown
  handleDeleteWorldbookEntry: (entry: ProjectWorldbookEntry) => unknown
  cancelWorldbookForm: () => unknown
  handleSubmitWorldbookEntry: () => unknown
}>()

const itemTypeLabels: Record<ProjectSearchResult['item_type'], string> = {
  chapter: 'Chapter',
  character: 'Character',
  glossary_term: 'Glossary',
  worldbook_entry: 'Worldbook',
}

const emit = defineEmits<{
  'update:projectSearchQuery': [value: string]
}>()

function updateProjectSearchQuery(value: string | number) {
  emit('update:projectSearchQuery', String(value))
}
</script>

<template>
  <div class="space-y-5">
    <div class="space-y-3 rounded-md border border-stone-300/80 bg-stone-100/80 p-4 dark:border-zinc-700/60 dark:bg-zinc-800/45">
      <div class="space-y-1">
        <p class="text-xs font-medium uppercase tracking-wider text-stone-700 dark:text-zinc-300">
          Project Search
        </p>
        <p class="text-xs text-stone-500 dark:text-zinc-400">
          Search chapters, characters, glossary terms, and worldbook entries.
        </p>
      </div>
      <div class="flex gap-2">
        <Input
          :model-value="props.projectSearchQuery"
          placeholder="Search project content"
          @update:modelValue="updateProjectSearchQuery"
          @keydown.enter="props.handleProjectSearch"
        />
        <Button
          variant="secondary"
          size="md"
          :loading="props.projectSearchLoading"
          :disabled="!props.projectSearchQuery.trim()"
          @click="props.handleProjectSearch"
        >
          Search
        </Button>
      </div>
      <Alert v-if="props.projectSearchError" variant="destructive" class="text-sm">
        {{ props.projectSearchError }}
      </Alert>
      <div v-if="props.projectSearchResults.length" class="space-y-2 max-h-64 overflow-y-auto pr-1">
        <button
          v-for="result in props.projectSearchResults"
          :key="`${result.item_type}:${result.item_id}`"
          type="button"
          class="w-full rounded-md border border-stone-300/80 bg-stone-50/90 p-3 text-left transition hover:border-amber-400/70 hover:bg-amber-50/80 dark:border-zinc-700/60 dark:bg-zinc-900/40 dark:hover:border-amber-600/70 dark:hover:bg-amber-900/15"
          @click="props.openProjectSearchResult(result)"
        >
          <div class="flex items-center justify-between gap-2">
            <p class="truncate text-sm font-medium text-stone-800 dark:text-zinc-100">
              {{ result.title }}
            </p>
            <span class="shrink-0 rounded-full bg-stone-200 px-2 py-0.5 text-[11px] text-stone-600 dark:bg-zinc-800 dark:text-zinc-300">
              {{ itemTypeLabels[result.item_type] }} · {{ result.matched_field }}
            </span>
          </div>
          <p class="mt-1 line-clamp-2 text-xs text-stone-600 dark:text-zinc-300">
            {{ result.snippet || 'Matched title' }}
          </p>
        </button>
      </div>
      <p v-else-if="props.projectSearchQuery.trim() && !props.projectSearchLoading && !props.projectSearchError" class="text-xs text-stone-500 dark:text-zinc-400">
        No matching project content.
      </p>
    </div>

    <div class="space-y-3 rounded-md border border-stone-300/80 bg-stone-100/80 p-4 dark:border-zinc-700/60 dark:bg-zinc-800/45">
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs font-medium uppercase tracking-wider text-stone-700 dark:text-zinc-300">
          Character Cards
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[11px] text-stone-500 dark:text-zinc-400">
            Selected {{ props.selectedCharactersCount }} ({{ props.characterSelectionCountLabel }})
          </span>
          <Button variant="ghost" size="sm" :loading="props.charactersLoading" @click="props.loadCharacters">Refresh</Button>
          <Button variant="secondary" size="sm" @click="props.beginCreateCharacter">+ Character</Button>
        </div>
      </div>

      <div v-if="props.projectCharacters.length" class="flex items-center gap-2">
        <Checkbox
          :model-value="props.allCharactersSelected"
          @update:modelValue="(value) => props.setAllCharactersSelected(Boolean(value))"
        />
        <span class="text-xs text-stone-600 dark:text-zinc-300">Select all cards for current operation</span>
      </div>

      <Alert v-if="props.charactersError" variant="destructive" class="text-sm">
        {{ props.charactersError }}
      </Alert>

      <div v-if="props.projectCharacters.length" class="space-y-2 max-h-60 overflow-y-auto pr-1">
        <div
          v-for="character in props.projectCharacters"
          :key="character.id"
          class="rounded-md border border-stone-300/80 bg-stone-50/90 p-3 dark:border-zinc-700/60 dark:bg-zinc-900/40"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 space-y-1">
              <div class="flex items-center gap-2">
                <Checkbox
                  :model-value="props.selectedCharacterIds.includes(character.id)"
                  @update:modelValue="(value) => props.toggleCharacterScope(character.id, Boolean(value))"
                />
                <p class="truncate text-sm font-medium text-stone-800 dark:text-zinc-100">
                  {{ character.name }}
                </p>
              </div>
              <p class="text-xs text-stone-500 dark:text-zinc-400">
                {{ character.role || 'Role not set' }}
              </p>
            </div>
            <div class="flex items-center gap-1">
              <Button variant="ghost" size="sm" @click="props.beginEditCharacter(character)">Edit</Button>
              <Button variant="ghost" size="sm" class="text-red-600 dark:text-red-300" @click="props.handleDeleteCharacter(character)">
                Delete
              </Button>
            </div>
          </div>
          <p v-if="character.profile" class="mt-2 line-clamp-2 text-xs text-stone-600 dark:text-zinc-300">
            {{ character.profile }}
          </p>
        </div>
      </div>
      <p v-else-if="!props.charactersLoading" class="text-xs text-stone-500 dark:text-zinc-400">
        No character cards yet. Add at least 1 to improve consistency in creation/continuation.
      </p>

      <div
        v-if="props.characterFormOpen"
        class="space-y-2 rounded-md border border-amber-300/70 bg-amber-100/80 p-3 dark:border-amber-700/50 dark:bg-amber-900/15"
      >
        <p class="text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-300">
          {{ props.editingCharacterId ? 'Edit Character Card' : 'Create Character Card' }}
        </p>
        <Input v-model="props.characterForm.name" placeholder="Name" />
        <Input v-model="props.characterForm.role" placeholder="Role (optional)" />
        <Textarea
          v-model="props.characterForm.profile"
          :rows="3"
          placeholder="Profile: personality, motivation, relationship, speaking style..."
        />
        <Textarea
          v-model="props.characterForm.notes"
          :rows="2"
          placeholder="Notes: constraints, timeline, taboo..."
        />
        <div class="flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" @click="props.cancelCharacterForm">Cancel</Button>
          <Button
            variant="secondary"
            size="sm"
            :loading="props.characterFormSubmitting"
            :disabled="!props.characterForm.name.trim()"
            @click="props.handleSubmitCharacter"
          >
            Save
          </Button>
        </div>
      </div>
    </div>

    <div class="space-y-3 rounded-md border border-stone-300/80 bg-stone-100/80 p-4 dark:border-zinc-700/60 dark:bg-zinc-800/45">
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs font-medium uppercase tracking-wider text-stone-700 dark:text-zinc-300">
          Glossary Terms
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[11px] text-stone-500 dark:text-zinc-400">
            Selected {{ props.selectedGlossaryTermsCount }} ({{ props.glossarySelectionCountLabel }})
          </span>
          <Button variant="ghost" size="sm" :loading="props.glossaryLoading" @click="props.loadGlossaryTerms">Refresh</Button>
          <Button variant="secondary" size="sm" @click="props.beginCreateGlossaryTerm">+ Term</Button>
        </div>
      </div>

      <div v-if="props.projectGlossaryTerms.length" class="flex items-center gap-2">
        <Checkbox
          :model-value="props.allGlossaryTermsSelected"
          @update:modelValue="(value) => props.setAllGlossaryTermsSelected(Boolean(value))"
        />
        <span class="text-xs text-stone-600 dark:text-zinc-300">Select all glossary terms for current operation</span>
      </div>

      <Alert v-if="props.glossaryError" variant="destructive" class="text-sm">
        {{ props.glossaryError }}
      </Alert>

      <div v-if="props.projectGlossaryTerms.length" class="space-y-2 max-h-52 overflow-y-auto pr-1">
        <div
          v-for="term in props.projectGlossaryTerms"
          :key="term.id"
          class="rounded-md border border-stone-300/80 bg-stone-50/90 p-3 dark:border-zinc-700/60 dark:bg-zinc-900/40"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 space-y-1">
              <div class="flex items-center gap-2">
                <Checkbox
                  :model-value="props.selectedGlossaryTermIds.includes(term.id)"
                  @update:modelValue="(value) => props.toggleGlossaryScope(term.id, Boolean(value))"
                />
                <p class="truncate text-sm font-medium text-stone-800 dark:text-zinc-100">
                  {{ term.term }}
                </p>
              </div>
              <p class="line-clamp-2 text-xs text-stone-600 dark:text-zinc-300">
                {{ term.definition || 'No definition' }}
              </p>
            </div>
            <div class="flex items-center gap-1">
              <Button variant="ghost" size="sm" @click="props.beginEditGlossaryTerm(term)">Edit</Button>
              <Button variant="ghost" size="sm" class="text-red-600 dark:text-red-300" @click="props.handleDeleteGlossaryTerm(term)">
                Delete
              </Button>
            </div>
          </div>
        </div>
      </div>
      <p v-else-if="!props.glossaryLoading" class="text-xs text-stone-500 dark:text-zinc-400">
        No glossary terms yet. Add domain terms to stabilize wording and references.
      </p>

      <div
        v-if="props.glossaryFormOpen"
        class="space-y-2 rounded-md border border-amber-300/70 bg-amber-100/80 p-3 dark:border-amber-700/50 dark:bg-amber-900/15"
      >
        <p class="text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-300">
          {{ props.editingGlossaryTermId ? 'Edit Glossary Term' : 'Create Glossary Term' }}
        </p>
        <Input v-model="props.glossaryForm.term" placeholder="Term" />
        <Textarea
          v-model="props.glossaryForm.definition"
          :rows="3"
          placeholder="Definition / meaning in this project context"
        />
        <Input v-model="props.glossaryForm.aliases" placeholder="Aliases, separated by comma" />
        <Textarea
          v-model="props.glossaryForm.notes"
          :rows="2"
          placeholder="Notes (optional)"
        />
        <div class="flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" @click="props.cancelGlossaryForm">Cancel</Button>
          <Button
            variant="secondary"
            size="sm"
            :loading="props.glossaryFormSubmitting"
            :disabled="!props.glossaryForm.term.trim()"
            @click="props.handleSubmitGlossaryTerm"
          >
            Save
          </Button>
        </div>
      </div>
    </div>

    <div class="space-y-3 rounded-md border border-stone-300/80 bg-stone-100/80 p-4 dark:border-zinc-700/60 dark:bg-zinc-800/45">
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs font-medium uppercase tracking-wider text-stone-700 dark:text-zinc-300">
          Worldbook Entries
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[11px] text-stone-500 dark:text-zinc-400">
            Selected {{ props.selectedWorldbookEntriesCount }} ({{ props.worldbookSelectionCountLabel }})
          </span>
          <Button variant="ghost" size="sm" :loading="props.worldbookLoading" @click="props.loadWorldbookEntries">Refresh</Button>
          <Button variant="secondary" size="sm" @click="props.beginCreateWorldbookEntry">+ Entry</Button>
        </div>
      </div>

      <div v-if="props.projectWorldbookEntries.length" class="flex items-center gap-2">
        <Checkbox
          :model-value="props.allWorldbookEntriesSelected"
          @update:modelValue="(value) => props.setAllWorldbookEntriesSelected(Boolean(value))"
        />
        <span class="text-xs text-stone-600 dark:text-zinc-300">Select all worldbook entries for current operation</span>
      </div>

      <Alert v-if="props.worldbookError" variant="destructive" class="text-sm">
        {{ props.worldbookError }}
      </Alert>

      <div v-if="props.projectWorldbookEntries.length" class="space-y-2 max-h-52 overflow-y-auto pr-1">
        <div
          v-for="entry in props.projectWorldbookEntries"
          :key="entry.id"
          class="rounded-md border border-stone-300/80 bg-stone-50/90 p-3 dark:border-zinc-700/60 dark:bg-zinc-900/40"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 space-y-1">
              <div class="flex items-center gap-2">
                <Checkbox
                  :model-value="props.selectedWorldbookEntryIds.includes(entry.id)"
                  @update:modelValue="(value) => props.toggleWorldbookScope(entry.id, Boolean(value))"
                />
                <p class="truncate text-sm font-medium text-stone-800 dark:text-zinc-100">
                  {{ entry.title }}
                </p>
              </div>
              <p class="text-xs text-stone-500 dark:text-zinc-400">
                {{ entry.category || 'Uncategorized' }}
              </p>
              <p class="line-clamp-2 text-xs text-stone-600 dark:text-zinc-300">
                {{ entry.content || 'No content' }}
              </p>
            </div>
            <div class="flex items-center gap-1">
              <Button variant="ghost" size="sm" @click="props.beginEditWorldbookEntry(entry)">Edit</Button>
              <Button variant="ghost" size="sm" class="text-red-600 dark:text-red-300" @click="props.handleDeleteWorldbookEntry(entry)">
                Delete
              </Button>
            </div>
          </div>
        </div>
      </div>
      <p v-else-if="!props.worldbookLoading" class="text-xs text-stone-500 dark:text-zinc-400">
        No worldbook entries yet. Add setting, factions, rules, and lore for stronger RAG grounding.
      </p>

      <div
        v-if="props.worldbookFormOpen"
        class="space-y-2 rounded-md border border-amber-300/70 bg-amber-100/80 p-3 dark:border-amber-700/50 dark:bg-amber-900/15"
      >
        <p class="text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-300">
          {{ props.editingWorldbookEntryId ? 'Edit Worldbook Entry' : 'Create Worldbook Entry' }}
        </p>
        <Input v-model="props.worldbookForm.title" placeholder="Title" />
        <Input v-model="props.worldbookForm.category" placeholder="Category (optional)" />
        <Input v-model="props.worldbookForm.tags" placeholder="Tags, separated by comma" />
        <Textarea
          v-model="props.worldbookForm.content"
          :rows="3"
          placeholder="Core world knowledge / lore / setting rules"
        />
        <Textarea
          v-model="props.worldbookForm.notes"
          :rows="2"
          placeholder="Notes (optional)"
        />
        <div class="flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" @click="props.cancelWorldbookForm">Cancel</Button>
          <Button
            variant="secondary"
            size="sm"
            :loading="props.worldbookFormSubmitting"
            :disabled="!props.worldbookForm.title.trim()"
            @click="props.handleSubmitWorldbookEntry"
          >
            Save
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
