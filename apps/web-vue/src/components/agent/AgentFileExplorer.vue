<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  Loader2,
  Plus,
  Trash2,
  Upload,
} from '@lucide/vue'
import { cn } from '@/lib/utils'
import AgentExplorerContextMenu from '@/components/agent/AgentExplorerContextMenu.vue'
import type { ProjectChapter } from '@/types'
import type { ProjectFile } from '@/api/projectFiles'

type ExplorerContextTarget =
  | { kind: 'chapter'; chapterId: string }
  | { kind: 'file'; path: string }

const props = defineProps<{
  chapters: ProjectChapter[]
  files: ProjectFile[]
  filesLoading: boolean
  activeKind: 'chapter' | 'file' | null
  activeChapterId: string
  activeFilePath: string
  searchQuery: string
  chapterImporting: boolean
  chapterImportMessage: string | null
  canDeleteChapter: boolean
  inlineRenameChapterId: string
  inlineRenameChapterTitle: string
  inlineRenameSubmitting: boolean
  inlineRenameFilePath: string
  inlineRenameFileName: string
  chapterAccept: string
}>()

const emit = defineEmits<{
  'update:searchQuery': [value: string]
  'update:inlineRenameChapterTitle': [value: string]
  'update:inlineRenameFileName': [value: string]
  selectChapter: [chapterId: string]
  selectFile: [path: string]
  createChapter: []
  deleteChapter: []
  importFiles: [event: Event]
  beginInlineRename: [chapterId: string]
  submitInlineRename: []
  cancelInlineRename: []
  beginInlineRenameFile: [path: string]
  submitInlineRenameFile: []
  cancelInlineRenameFile: []
  renameChapter: [chapterId: string]
  deleteChapterById: [chapterId: string]
  renameFile: [path: string]
  deleteFile: [path: string]
}>()

const { t } = useI18n()

const chaptersExpanded = ref(true)
const filesExpanded = ref(true)
const chapterFileInput = ref<HTMLInputElement | null>(null)

const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  target: null as ExplorerContextTarget | null,
})

const searchQueryValue = computed({
  get: () => props.searchQuery,
  set: (value: string) => emit('update:searchQuery', value),
})

const inlineRenameTitleValue = computed({
  get: () => props.inlineRenameChapterTitle,
  set: (value: string) => emit('update:inlineRenameChapterTitle', value),
})

const inlineRenameFileNameValue = computed({
  get: () => props.inlineRenameFileName,
  set: (value: string) => emit('update:inlineRenameFileName', value),
})

const filteredChapters = computed(() => {
  const query = props.searchQuery.trim().toLowerCase()
  if (!query) return props.chapters
  return props.chapters.filter((chapter) =>
    `${chapter.title} ${chapter.content}`.toLowerCase().includes(query)
  )
})

const filteredFiles = computed(() => {
  const query = props.searchQuery.trim().toLowerCase()
  if (!query) return props.files
  return props.files.filter((file) =>
    `${file.name} ${file.path}`.toLowerCase().includes(query)
  )
})

const contextMenuStyle = computed(() => {
  const width = 176
  const height = 72
  const margin = 8
  const maxX = Math.max(margin, window.innerWidth - width - margin)
  const maxY = Math.max(margin, window.innerHeight - height - margin)
  return {
    left: `${Math.min(Math.max(contextMenu.value.x, margin), maxX)}px`,
    top: `${Math.min(Math.max(contextMenu.value.y, margin), maxY)}px`,
  }
})

function openFilePicker() {
  chapterFileInput.value?.click()
}

function isInlineRenamingChapter(chapterId: string): boolean {
  return props.inlineRenameChapterId === chapterId
}

function isInlineRenamingFile(path: string): boolean {
  return props.inlineRenameFilePath === path
}

function chapterLabel(chapter: ProjectChapter): string {
  return chapter.title || t('agent.editor.chapterFallback', { index: chapter.order_index + 1 })
}

function openContextMenu(event: MouseEvent, target: ExplorerContextTarget) {
  event.preventDefault()
  event.stopPropagation()
  contextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    target,
  }
}

function closeContextMenu() {
  contextMenu.value.visible = false
  contextMenu.value.target = null
}

function handleContextMenuRename() {
  const target = contextMenu.value.target
  closeContextMenu()
  if (!target) return
  if (target.kind === 'chapter') {
    emit('renameChapter', target.chapterId)
  } else {
    emit('renameFile', target.path)
  }
}

function handleContextMenuDelete() {
  const target = contextMenu.value.target
  closeContextMenu()
  if (!target) return
  if (target.kind === 'chapter') {
    emit('deleteChapterById', target.chapterId)
  } else {
    emit('deleteFile', target.path)
  }
}

function handleGlobalPointerDown(event: PointerEvent) {
  if (!contextMenu.value.visible) return
  const el = event.target as HTMLElement | null
  if (el?.closest?.('[data-agent-explorer-context-menu="true"]')) return
  closeContextMenu()
}

function handleGlobalKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && contextMenu.value.visible) {
    closeContextMenu()
  }
}

onMounted(() => {
  window.addEventListener('pointerdown', handleGlobalPointerDown)
  window.addEventListener('keydown', handleGlobalKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointerdown', handleGlobalPointerDown)
  window.removeEventListener('keydown', handleGlobalKeyDown)
})
</script>

<template>
  <aside class="muse-explorer" data-testid="agent-file-explorer">
    <div class="muse-explorer-header">
      <span class="muse-explorer-title">{{ t('agent.editor.explorerTitle') }}</span>
    </div>

    <div class="muse-explorer-search">
      <input
        v-model="searchQueryValue"
        type="search"
        class="muse-explorer-search-input"
        :placeholder="t('agent.editor.searchPlaceholder')"
        data-testid="agent-explorer-search"
      />
    </div>

    <input
      ref="chapterFileInput"
      type="file"
      multiple
      :accept="chapterAccept"
      class="hidden"
      @change="emit('importFiles', $event)"
    />

    <div class="muse-explorer-actions">
      <button
        type="button"
        class="muse-explorer-action-btn"
        :title="t('agent.editor.newChapter')"
        data-testid="agent-new-chapter"
        @click="emit('createChapter')"
      >
        <Plus class="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        class="muse-explorer-action-btn"
        :title="t('agent.editor.importChapters')"
        :disabled="chapterImporting"
        @click="openFilePicker"
      >
        <Loader2 v-if="chapterImporting" class="h-3.5 w-3.5 animate-spin" />
        <Upload v-else class="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        class="muse-explorer-action-btn"
        :title="t('agent.editor.delete')"
        :disabled="!canDeleteChapter"
        data-testid="agent-delete-chapter"
        @click="emit('deleteChapter')"
      >
        <Trash2 class="h-3.5 w-3.5" />
      </button>
    </div>

    <p v-if="chapterImportMessage" class="muse-explorer-message">
      {{ chapterImportMessage }}
    </p>

    <div class="muse-explorer-body">
      <section class="muse-explorer-section">
        <button
          type="button"
          class="muse-explorer-section-header"
          @click="chaptersExpanded = !chaptersExpanded"
        >
          <component :is="chaptersExpanded ? ChevronDown : ChevronRight" class="h-3 w-3 shrink-0" />
          <FolderOpen class="h-3.5 w-3.5 shrink-0 muse-text-muted" />
          <span>{{ t('agent.editor.explorerChapters') }}</span>
          <span class="ml-auto text-[10px] muse-text-faint">{{ filteredChapters.length }}</span>
        </button>
        <div v-show="chaptersExpanded" class="muse-explorer-tree">
          <div
            v-for="chapter in filteredChapters"
            :key="chapter.id"
            :class="cn(
              'muse-explorer-item',
              activeKind === 'chapter' && activeChapterId === chapter.id && 'muse-explorer-item-active'
            )"
            data-testid="agent-explorer-chapter-item"
            @click="emit('selectChapter', chapter.id)"
            @contextmenu="openContextMenu($event, { kind: 'chapter', chapterId: chapter.id })"
          >
            <FileText class="h-3.5 w-3.5 shrink-0 muse-text-faint" />
            <div class="min-w-0 flex-1">
              <input
                v-if="isInlineRenamingChapter(chapter.id)"
                v-model="inlineRenameTitleValue"
                autofocus
                class="muse-explorer-rename-input"
                :disabled="inlineRenameSubmitting"
                @click.stop
                @keydown.enter.prevent="emit('submitInlineRename')"
                @keydown.esc.prevent="emit('cancelInlineRename')"
                @blur="emit('submitInlineRename')"
              />
              <p
                v-else
                class="truncate text-xs font-medium muse-text-body"
                @dblclick.stop="emit('beginInlineRename', chapter.id)"
              >
                {{ chapterLabel(chapter) }}
              </p>
              <p class="truncate text-[10px] muse-text-faint">
                {{ t('agent.editor.chapterMeta', { chars: (chapter.content || '').length.toLocaleString() }) }}
              </p>
            </div>
          </div>
          <p v-if="!filteredChapters.length" class="muse-explorer-empty">
            {{ t('agent.editor.noChapters') }}
          </p>
        </div>
      </section>

      <section class="muse-explorer-section">
        <button
          type="button"
          class="muse-explorer-section-header"
          @click="filesExpanded = !filesExpanded"
        >
          <component :is="filesExpanded ? ChevronDown : ChevronRight" class="h-3 w-3 shrink-0" />
          <FolderOpen class="h-3.5 w-3.5 shrink-0 muse-text-muted" />
          <span>{{ t('agent.editor.explorerFiles') }}</span>
          <Loader2 v-if="filesLoading" class="ml-auto h-3 w-3 animate-spin muse-text-faint" />
          <span v-else class="ml-auto text-[10px] muse-text-faint">{{ filteredFiles.length }}</span>
        </button>
        <div v-show="filesExpanded" class="muse-explorer-tree">
          <div
            v-for="file in filteredFiles"
            :key="file.path"
            :class="cn(
              'muse-explorer-item',
              activeKind === 'file' && activeFilePath === file.path && 'muse-explorer-item-active',
              !file.text_extractable && 'opacity-60'
            )"
            data-testid="agent-explorer-file-item"
            @click="file.text_extractable && emit('selectFile', file.path)"
            @contextmenu="openContextMenu($event, { kind: 'file', path: file.path })"
          >
            <FileText class="h-3.5 w-3.5 shrink-0 muse-text-faint" />
            <div class="min-w-0 flex-1">
              <input
                v-if="isInlineRenamingFile(file.path)"
                v-model="inlineRenameFileNameValue"
                autofocus
                class="muse-explorer-rename-input"
                :disabled="inlineRenameSubmitting"
                @click.stop
                @keydown.enter.prevent="emit('submitInlineRenameFile')"
                @keydown.esc.prevent="emit('cancelInlineRenameFile')"
                @blur="emit('submitInlineRenameFile')"
              />
              <p
                v-else
                class="truncate text-xs font-medium muse-text-body"
                @dblclick.stop="emit('beginInlineRenameFile', file.path)"
              >
                {{ file.name }}
              </p>
              <p class="truncate text-[10px] muse-text-faint">{{ file.path }}</p>
            </div>
          </div>
          <p v-if="filesLoading" class="muse-explorer-empty">{{ t('agent.editor.loadingFiles') }}</p>
          <p v-else-if="!filteredFiles.length" class="muse-explorer-empty">
            {{ t('agent.editor.noFiles') }}
          </p>
        </div>
      </section>
    </div>

    <AgentExplorerContextMenu
      :visible="contextMenu.visible"
      :style="contextMenuStyle"
      @rename="handleContextMenuRename"
      @delete="handleContextMenuDelete"
    />
  </aside>
</template>
