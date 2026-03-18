<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ProjectChapter } from '@/types'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Input from '@/components/ui/Input.vue'

const props = defineProps<{
  leftPanelCollapsed: boolean
  chapterAccept: string
  chapterSaving: boolean
  chapterImporting: boolean
  chapterImportMessage: string | null
  selectedChapterIds: string[]
  activeChapterId: string
  filteredChapters: ProjectChapter[]
  chapterSearchQuery: string
  inlineRenameChapterId: string
  inlineRenameChapterTitle: string
  inlineRenameSubmitting: boolean
  canDeleteChapter: boolean
}>()

const emit = defineEmits<{
  'update:chapterSearchQuery': [value: string]
  'update:inlineRenameChapterTitle': [value: string]
  importFiles: [event: Event]
  createChapter: []
  deleteActiveChapter: []
  openContextMenu: [event: MouseEvent, chapterId: string]
  toggleChapterScope: [chapterId: string]
  selectChapter: [chapterId: string]
  beginInlineRename: [chapterId: string]
  submitInlineRename: []
  cancelInlineRename: []
}>()

const chapterFileInput = ref<HTMLInputElement | null>(null)

const chapterSearchQueryValue = computed({
  get: () => props.chapterSearchQuery,
  set: (value: string | number) => emit('update:chapterSearchQuery', String(value || '')),
})

const inlineRenameChapterTitleValue = computed({
  get: () => props.inlineRenameChapterTitle,
  set: (value: string | number) => emit('update:inlineRenameChapterTitle', String(value || '')),
})

function openChapterFilePicker() {
  chapterFileInput.value?.click()
}

function isInlineRenamingChapter(chapterId: string): boolean {
  return props.inlineRenameChapterId === chapterId
}
</script>

<template>
  <aside
    class="shrink-0 border-r border-stone-300/80 bg-[#f2ecdf] transition-all duration-200 dark:border-zinc-700/60 dark:bg-zinc-900/50"
    :class="leftPanelCollapsed ? 'w-0 overflow-hidden border-r-0 p-0' : 'w-72 p-3'"
  >
    <template v-if="!leftPanelCollapsed">
      <input
        ref="chapterFileInput"
        type="file"
        multiple
        :accept="chapterAccept"
        class="hidden"
        @change="emit('importFiles', $event)"
      />

      <div class="mb-3 flex items-center justify-between">
        <p class="text-[11px] uppercase tracking-wider text-stone-500 dark:text-zinc-500">
          Files (Chapters)
        </p>
        <span class="text-[10px] text-stone-500 dark:text-zinc-500">
          Scope {{ selectedChapterIds.length }}
        </span>
      </div>

      <div class="mb-3 flex flex-wrap gap-2">
        <Button variant="ghost" size="sm" :disabled="chapterSaving" @click="emit('createChapter')">+ Chapter</Button>
        <Button variant="ghost" size="sm" :loading="chapterImporting" :disabled="chapterImporting" @click="openChapterFilePicker">
          Import
        </Button>
        <Button variant="ghost" size="sm" :disabled="!canDeleteChapter" @click="emit('deleteActiveChapter')">Delete</Button>
      </div>

      <Input
        v-model="chapterSearchQueryValue"
        class="mb-2"
        placeholder="Search chapters"
      />

      <p v-if="chapterImportMessage" class="mb-2 text-xs text-amber-700 dark:text-amber-300">
        {{ chapterImportMessage }}
      </p>

      <div class="max-h-[calc(100%-150px)] space-y-1 overflow-y-auto pr-1">
        <div
          v-for="chapter in filteredChapters"
          :key="`scope-${chapter.id}`"
          class="flex items-center gap-2 rounded border px-2 py-1.5 transition-colors"
          :class="
            activeChapterId === chapter.id
              ? 'border-amber-500/70 bg-amber-100/70 dark:bg-amber-900/20'
              : 'border-stone-300 bg-stone-50/80 hover:bg-stone-100 dark:border-zinc-700 dark:bg-zinc-800/60 dark:hover:bg-zinc-800'
          "
          @contextmenu.prevent="emit('openContextMenu', $event, chapter.id)"
        >
          <Checkbox
            :model-value="selectedChapterIds.includes(chapter.id)"
            @click.stop
            @update:modelValue="() => emit('toggleChapterScope', chapter.id)"
          />
          <div class="min-w-0 flex-1 cursor-pointer" @click="emit('selectChapter', chapter.id)">
            <input
              v-if="isInlineRenamingChapter(chapter.id)"
              v-model="inlineRenameChapterTitleValue"
              autofocus
              class="h-7 w-full rounded-md border border-amber-400 bg-stone-50 px-2 text-xs font-medium text-stone-800 outline-none ring-2 ring-amber-300/40 dark:border-amber-500/70 dark:bg-zinc-900 dark:text-zinc-100 dark:ring-amber-500/30"
              :disabled="inlineRenameSubmitting"
              @click.stop
              @keydown.enter.prevent="emit('submitInlineRename')"
              @keydown.esc.prevent="emit('cancelInlineRename')"
              @blur="emit('submitInlineRename')"
            />
            <p
              v-else
              class="truncate text-xs font-medium"
              :class="activeChapterId === chapter.id ? 'text-amber-700 dark:text-amber-300' : 'text-stone-700 dark:text-zinc-200'"
              @dblclick.stop="emit('beginInlineRename', chapter.id)"
            >
              {{ chapter.title || `Chapter ${chapter.order_index + 1}` }}
            </p>
            <p class="text-[10px] text-stone-500 dark:text-zinc-500">
              #{{ chapter.order_index + 1 }} · {{ (chapter.content || '').length.toLocaleString() }} chars
            </p>
          </div>
        </div>
        <p v-if="!filteredChapters.length" class="px-1 py-2 text-xs text-stone-500 dark:text-zinc-500">
          No matching chapters
        </p>
      </div>
    </template>
  </aside>
</template>
