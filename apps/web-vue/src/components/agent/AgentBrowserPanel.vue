<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { BookOpen, FilePlus2, GitCommit, Loader2, Save, Upload } from '@lucide/vue'
import {
  createProjectFile,
  deleteProjectFile,
  listProjectFiles,
  readProjectFile,
  updateProjectFile,
  uploadProjectFile,
  type ProjectFile,
} from '@/api/projectFiles'
import { listKnowledge, type KnowledgeSnapshot } from '@/api/memory'
import { getProjectVersions, restoreProjectVersion } from '@/api/projectVersions'
import { useAgentStore } from '@/stores/agent'
import { useProjectStore } from '@/stores/project'
import type { ProjectRevision } from '@/types'

const props = defineProps<{ projectId: string }>()
const projectStore = useProjectStore()
const agentStore = useAgentStore()
const tab = ref<'files' | 'knowledge' | 'versions'>('files')
const loading = ref(false)
const files = ref<ProjectFile[]>([])
const selectedPath = ref('')
const editorContent = ref('')
const editorDirty = ref(false)
const knowledge = ref<KnowledgeSnapshot | null>(null)
const versions = ref<ProjectRevision[]>([])
const newPath = ref('')
const uploadInput = ref<HTMLInputElement | null>(null)

const canEdit = computed(() => projectStore.currentProject?.current_user_permissions?.includes('edit'))

async function loadFiles() {
  files.value = await listProjectFiles(props.projectId)
  if (selectedPath.value && !files.value.some((item) => item.path === selectedPath.value)) {
    selectedPath.value = ''
    editorContent.value = ''
  }
}

async function selectFile(path: string) {
  const result = await readProjectFile(props.projectId, path)
  selectedPath.value = path
  editorContent.value = result.content
  editorDirty.value = false
}

async function saveFile() {
  if (!selectedPath.value) return
  await updateProjectFile(props.projectId, selectedPath.value, editorContent.value)
  editorDirty.value = false
  await Promise.all([loadFiles(), projectStore.fetchProject(props.projectId)])
}

async function createFile() {
  const path = newPath.value.trim()
  if (!path) return
  await createProjectFile(props.projectId, path)
  newPath.value = ''
  await loadFiles()
  await selectFile(path)
}

async function removeFile(path: string) {
  await deleteProjectFile(props.projectId, path)
  await loadFiles()
  await projectStore.fetchProject(props.projectId)
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await uploadProjectFile(props.projectId, file)
  input.value = ''
  await Promise.all([loadFiles(), projectStore.fetchProject(props.projectId)])
}

async function loadTab() {
  loading.value = true
  try {
    if (tab.value === 'files') await loadFiles()
    else if (tab.value === 'knowledge') knowledge.value = await listKnowledge(props.projectId)
    else versions.value = await getProjectVersions(props.projectId)
  } finally {
    loading.value = false
  }
}

async function restore(revisionId: string) {
  const run = await restoreProjectVersion(props.projectId, revisionId)
  await agentStore.loadRuns(props.projectId)
  await agentStore.selectRun(props.projectId, run.id)
}

onMounted(loadTab)
watch(tab, loadTab)
watch(() => props.projectId, async () => {
  selectedPath.value = ''
  editorContent.value = ''
  knowledge.value = null
  versions.value = []
  await loadTab()
})
</script>

<template>
  <aside class="flex min-h-0 flex-col border-l border-[color:var(--muse-border)] bg-[color:var(--muse-surface)]">
    <div class="grid grid-cols-3 border-b border-[color:var(--muse-border)]">
      <button class="px-2 py-3 text-xs" :class="{ 'font-semibold muse-text-heading': tab === 'files' }" @click="tab = 'files'">文件</button>
      <button class="px-2 py-3 text-xs" :class="{ 'font-semibold muse-text-heading': tab === 'knowledge' }" @click="tab = 'knowledge'">知识</button>
      <button class="px-2 py-3 text-xs" :class="{ 'font-semibold muse-text-heading': tab === 'versions' }" @click="tab = 'versions'">版本</button>
    </div>

    <div v-if="loading" class="flex flex-1 items-center justify-center">
      <Loader2 class="h-5 w-5 animate-spin muse-text-faint" />
    </div>

    <div v-else-if="tab === 'files'" class="flex min-h-0 flex-1 flex-col">
      <div v-if="canEdit" class="flex gap-2 border-b border-[color:var(--muse-border)] p-2">
        <input v-model="newPath" class="muse-input min-w-0 flex-1 text-xs" placeholder="drafts/chapter-01.md" @keydown.enter="createFile" />
        <button class="muse-icon-btn" type="button" title="新建文件" @click="createFile"><FilePlus2 class="h-4 w-4" /></button>
        <button class="muse-icon-btn" type="button" title="上传文件" @click="uploadInput?.click()"><Upload class="h-4 w-4" /></button>
        <input ref="uploadInput" class="hidden" type="file" @change="upload" />
      </div>
      <div class="max-h-48 overflow-y-auto border-b border-[color:var(--muse-border)] p-2">
        <div v-for="file in files" :key="file.path" class="group flex items-center gap-1">
          <button class="min-w-0 flex-1 truncate rounded px-2 py-1.5 text-left text-xs hover:bg-[color:var(--muse-surface-muted)]" :class="{ 'font-semibold': selectedPath === file.path }" @click="selectFile(file.path)">
            {{ file.path }}
          </button>
          <button v-if="canEdit" class="hidden px-1 text-xs text-red-500 group-hover:block" type="button" @click="removeFile(file.path)">×</button>
        </div>
      </div>
      <template v-if="selectedPath">
        <div class="flex items-center gap-2 border-b border-[color:var(--muse-border)] px-3 py-2">
          <span class="min-w-0 flex-1 truncate text-xs font-medium">{{ selectedPath }}</span>
          <button v-if="canEdit" class="muse-icon-btn" type="button" :disabled="!editorDirty" @click="saveFile"><Save class="h-4 w-4" /></button>
        </div>
        <textarea
          v-model="editorContent"
          class="min-h-0 flex-1 resize-none bg-transparent p-4 font-mono text-xs leading-5 outline-none"
          :readonly="!canEdit"
          @input="editorDirty = true"
        />
      </template>
      <div v-else class="flex flex-1 items-center justify-center px-6 text-center text-xs muse-text-faint">选择 Git 项目文件进行查看或编辑</div>
    </div>

    <div v-else-if="tab === 'knowledge'" class="min-h-0 flex-1 overflow-y-auto p-3">
      <div class="mb-3 rounded-lg bg-[color:var(--muse-surface-muted)] p-3 text-xs">
        <p class="font-semibold">{{ knowledge?.dataset_name }}</p>
        <p class="mt-1 muse-text-faint">不可变 Cognee Dataset · {{ knowledge?.records.length || 0 }} 条记录</p>
      </div>
      <article v-for="record in knowledge?.records || []" :key="record.id" class="mb-3 rounded-lg border border-[color:var(--muse-border)] p-3">
        <div class="flex items-center gap-2">
          <BookOpen class="h-3.5 w-3.5 muse-text-faint" />
          <p class="min-w-0 flex-1 truncate text-xs font-semibold">{{ record.title }}</p>
          <code class="text-[10px] muse-text-faint">{{ record.kind }}</code>
        </div>
        <p class="mt-2 whitespace-pre-wrap text-xs leading-5 muse-text-body">{{ record.content }}</p>
        <details class="mt-2 text-[11px]">
          <summary class="cursor-pointer muse-text-faint">来源与属性</summary>
          <pre class="mt-2 overflow-auto whitespace-pre-wrap">{{ JSON.stringify({ id: record.id, sources: record.source_refs, attributes: record.attributes }, null, 2) }}</pre>
        </details>
      </article>
    </div>

    <div v-else class="min-h-0 flex-1 overflow-y-auto p-3">
      <article v-for="revision in versions" :key="revision.id" class="mb-3 rounded-lg border border-[color:var(--muse-border)] p-3">
        <div class="flex items-center gap-2">
          <GitCommit class="h-4 w-4 muse-text-faint" />
          <p class="min-w-0 flex-1 truncate text-xs font-semibold">{{ revision.message }}</p>
          <span class="text-[10px] muse-text-faint">{{ revision.status }}</span>
        </div>
        <code class="mt-2 block truncate text-[10px] muse-text-faint">{{ revision.git_commit }}</code>
        <p class="mt-1 truncate text-[10px] muse-text-faint">{{ revision.knowledge_dataset }}</p>
        <button v-if="revision.status !== 'active' && canEdit" class="muse-btn muse-btn-secondary mt-3 w-full text-xs" type="button" @click="restore(revision.id)">
          创建恢复审核
        </button>
      </article>
    </div>
  </aside>
</template>
