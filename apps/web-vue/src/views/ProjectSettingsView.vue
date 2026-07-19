<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, Loader2, Save, Trash2, UserPlus } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { useProjectStore } from '@/stores/project'
import {
  addProjectMember,
  deleteProjectMember,
  getEmbeddingModels,
  getModels,
  getRerankerModels,
  listProjectMembers,
  updateProjectMember,
  updateProjectVisibility,
  type ModelInfo,
  type ProjectMember,
} from '@/api/projects'
import { listKnowledge, type KnowledgeSnapshot } from '@/api/memory'
import { downloadBlob, downloadProjectBundle } from '@/api/export'

const route = useRoute()
const router = useRouter()
const projects = useProjectStore()
const projectId = computed(() => String(route.params.id || ''))
const loading = ref(false)
const saving = ref(false)
const chatModels = ref<ModelInfo[]>([])
const embeddingModels = ref<ModelInfo[]>([])
const rerankerModels = ref<ModelInfo[]>([])
const knowledge = ref<KnowledgeSnapshot | null>(null)
const members = ref<ProjectMember[]>([])
const memberUserId = ref('')
const memberRole = ref<'editor' | 'viewer'>('viewer')
const form = reactive({
  title: '',
  description: '',
  pack_slug: 'generic',
  component_models: {} as Record<string, string>,
})

const canManage = computed(() => projects.currentProject?.current_user_permissions?.includes('manage'))
const canDelete = computed(() => projects.currentProject?.current_user_permissions?.includes('delete'))

async function load() {
  loading.value = true
  try {
    const [project, chats, embeddings, rerankers, snapshot, projectMembers] = await Promise.all([
      projects.fetchProject(projectId.value),
      getModels(),
      getEmbeddingModels(),
      getRerankerModels(),
      listKnowledge(projectId.value),
      listProjectMembers(projectId.value),
    ])
    chatModels.value = chats
    embeddingModels.value = embeddings
    rerankerModels.value = rerankers
    knowledge.value = snapshot
    members.value = projectMembers
    form.title = project.title
    form.description = project.description || ''
    form.pack_slug = project.pack_slug
    form.component_models = { ...(project.component_models || {}) }
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await projects.updateProject(projectId.value, {
      title: form.title,
      description: form.description,
      pack_slug: form.pack_slug,
      component_models: form.component_models,
    })
  } finally {
    saving.value = false
  }
}

async function setVisibility(publicProject: boolean) {
  await updateProjectVisibility(projectId.value, publicProject ? 'public' : 'private')
  await projects.fetchProject(projectId.value)
}

async function addMember() {
  const member = await addProjectMember(projectId.value, memberUserId.value.trim(), memberRole.value)
  members.value.push(member)
  memberUserId.value = ''
}

async function changeRole(member: ProjectMember, role: 'editor' | 'viewer') {
  const updated = await updateProjectMember(projectId.value, member.id, role)
  members.value = members.value.map((item) => item.id === updated.id ? updated : item)
}

async function removeMember(member: ProjectMember) {
  await deleteProjectMember(projectId.value, member.id)
  members.value = members.value.filter((item) => item.id !== member.id)
}

async function exportBundle() {
  const blob = await downloadProjectBundle(projectId.value)
  downloadBlob(blob, `${form.title.replace(/[^\w.-]+/g, '_') || 'project'}.zip`)
}

async function removeProject() {
  if (!window.confirm(`确认删除项目「${form.title}」？Git、知识与任务数据都会删除。`)) return
  await projects.deleteProject(projectId.value)
  await router.push('/projects')
}

function setModel(key: string, value: string) {
  const next = { ...form.component_models }
  if (value.trim()) next[key] = value.trim()
  else delete next[key]
  form.component_models = next
}

watch(projectId, load, { immediate: true })
</script>

<template>
  <AppLayout>
    <div class="mx-auto max-w-4xl space-y-5 py-6">
      <router-link :to="`/projects/${projectId}`" class="inline-flex items-center gap-1 text-sm muse-text-muted">
        <ArrowLeft class="h-4 w-4" />返回工作区
      </router-link>
      <div v-if="loading" class="flex justify-center py-20"><Loader2 class="h-5 w-5 animate-spin" /></div>
      <template v-else>
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-xl font-semibold muse-text-heading">项目设置</h1>
            <p class="mt-1 text-sm muse-text-muted">配置 Text Pack、Agent 模型、Cognee 模型与成员权限。</p>
          </div>
          <div class="flex gap-2">
            <Button variant="secondary" @click="router.push(`/projects/${projectId}/agents`)">Agents</Button>
            <Button variant="secondary" @click="router.push(`/projects/${projectId}/skills`)">Skills</Button>
            <Button variant="secondary" @click="router.push(`/projects/${projectId}/versions`)">版本</Button>
          </div>
        </div>

        <Card class="space-y-4 p-5">
          <h2 class="text-sm font-semibold">基础信息</h2>
          <input v-model="form.title" class="muse-input w-full" :disabled="!canManage" />
          <textarea v-model="form.description" class="muse-input min-h-24 w-full" :disabled="!canManage" />
          <select v-model="form.pack_slug" class="muse-input w-full" :disabled="!canManage">
            <option v-for="pack in ['generic','novel','article','paper','screenplay','product_doc']" :key="pack" :value="pack">{{ pack }}</option>
          </select>
          <label v-if="canManage" class="flex items-center gap-2 text-sm">
            <input type="checkbox" :checked="projects.currentProject?.visibility === 'public'" @change="setVisibility(($event.target as HTMLInputElement).checked)" />
            公开项目
          </label>
        </Card>

        <Card class="space-y-4 p-5">
          <h2 class="text-sm font-semibold">Agent 与记忆模型</h2>
          <label v-for="[key, label] in [
            ['operation_agent_task','创作'],
            ['operation_analyze','分析'],
            ['operation_agent_suggest','建议'],
            ['memory_llm','Cognee LLM'],
          ]" :key="key" class="grid gap-2 text-xs sm:grid-cols-[180px_1fr] sm:items-center">
            <span>{{ label }}</span>
            <select :value="form.component_models[key] || ''" class="muse-input" :disabled="!canManage" @change="setModel(key, ($event.target as HTMLSelectElement).value)">
              <option value="">未配置</option>
              <option v-for="model in chatModels" :key="model.id" :value="model.id">{{ model.id }}</option>
            </select>
          </label>
          <label class="grid gap-2 text-xs sm:grid-cols-[180px_1fr] sm:items-center">
            <span>Cognee Embedding</span>
            <select :value="form.component_models.memory_embedding || ''" class="muse-input" :disabled="!canManage" @change="setModel('memory_embedding', ($event.target as HTMLSelectElement).value)">
              <option value="">未配置</option>
              <option v-for="model in embeddingModels" :key="model.id" :value="model.id">{{ model.id }}</option>
            </select>
          </label>
          <label class="grid gap-2 text-xs sm:grid-cols-[180px_1fr] sm:items-center">
            <span>Embedding 维度</span>
            <input :value="form.component_models.memory_embedding_dimensions || ''" type="number" min="1" class="muse-input" :disabled="!canManage" @input="setModel('memory_embedding_dimensions', ($event.target as HTMLInputElement).value)" />
          </label>
          <label class="grid gap-2 text-xs sm:grid-cols-[180px_1fr] sm:items-center">
            <span>知识 Reranker</span>
            <select :value="form.component_models.memory_reranker || ''" class="muse-input" :disabled="!canManage" @change="setModel('memory_reranker', ($event.target as HTMLSelectElement).value)">
              <option value="">未配置</option>
              <option v-for="model in rerankerModels" :key="model.id" :value="model.id">{{ model.id }}</option>
            </select>
          </label>
          <div class="rounded-lg bg-[color:var(--muse-surface-muted)] p-3 text-xs">
            <p class="font-semibold">{{ knowledge?.dataset_name }}</p>
            <p class="mt-1 muse-text-faint">{{ knowledge?.records.length || 0 }} 条结构化知识</p>
          </div>
        </Card>

        <Card class="space-y-4 p-5">
          <h2 class="text-sm font-semibold">成员</h2>
          <div v-for="member in members" :key="member.id" class="flex items-center gap-2 rounded border border-[color:var(--muse-border)] p-2">
            <code class="min-w-0 flex-1 truncate text-xs">{{ member.user_id }}</code>
            <select :value="member.role" class="muse-input text-xs" :disabled="member.role === 'owner' || !canManage" @change="changeRole(member, ($event.target as HTMLSelectElement).value as 'editor' | 'viewer')">
              <option value="owner">owner</option><option value="editor">editor</option><option value="viewer">viewer</option>
            </select>
            <button v-if="member.role !== 'owner' && canManage" type="button" class="muse-icon-btn" @click="removeMember(member)"><Trash2 class="h-4 w-4" /></button>
          </div>
          <div v-if="canManage" class="flex gap-2">
            <input v-model="memberUserId" class="muse-input min-w-0 flex-1" placeholder="用户 ID" />
            <select v-model="memberRole" class="muse-input"><option value="editor">editor</option><option value="viewer">viewer</option></select>
            <Button :disabled="!memberUserId.trim()" @click="addMember"><UserPlus class="h-4 w-4" /></Button>
          </div>
        </Card>

        <div class="flex flex-wrap justify-between gap-3">
          <Button variant="secondary" @click="exportBundle"><Download class="mr-1 h-4 w-4" />导出</Button>
          <div class="flex gap-2">
            <Button v-if="canDelete" variant="danger" @click="removeProject"><Trash2 class="mr-1 h-4 w-4" />删除项目</Button>
            <Button v-if="canManage" :loading="saving" @click="save"><Save class="mr-1 h-4 w-4" />保存设置</Button>
          </div>
        </div>
      </template>
    </div>
  </AppLayout>
</template>
