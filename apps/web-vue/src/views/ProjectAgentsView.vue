<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Check, Plus, Save, Trash2 } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Button from '@/components/ui/Button.vue'
import Card from '@/components/ui/Card.vue'
import {
  activateProjectAgent,
  createProjectAgent,
  deleteProjectAgent,
  listProjectAgents,
  listPromptTemplates,
  updateProjectAgent,
} from '@/api/agentConfiguration'
import { getModels, type ModelInfo } from '@/api/projects'
import { useProjectStore } from '@/stores/project'
import type { ProjectAgent, PromptPhase, PromptTemplate } from '@/types'

const route = useRoute()
const projects = useProjectStore()
const projectId = computed(() => String(route.params.id || ''))
const phases: PromptPhase[] = ['architect', 'planner', 'writer', 'auditor', 'reviser']
const agents = ref<ProjectAgent[]>([])
const templates = ref<PromptTemplate[]>([])
const models = ref<ModelInfo[]>([])
const selectedId = ref('')
const saving = ref(false)
const form = reactive({
  name: '',
  description: '',
  model: '',
  effort: '' as '' | 'low' | 'medium' | 'high',
  prompt_template_ids: {} as Partial<Record<PromptPhase, string>>,
  enabled: true,
})
const activeId = computed(() => projects.currentProject?.active_agent_id || '')
const canManage = computed(() => projects.currentProject?.current_user_permissions?.includes('manage'))

async function load() {
  const [projectAgents, accountTemplates, availableModels] = await Promise.all([
    listProjectAgents(projectId.value),
    listPromptTemplates(),
    getModels(projectId.value),
  ])
  agents.value = projectAgents
  templates.value = accountTemplates
  models.value = availableModels
  if (!projects.currentProject) await projects.fetchProject(projectId.value)
  if (selectedId.value) select(agents.value.find((item) => item.id === selectedId.value))
  else select(agents.value.find((item) => item.id === activeId.value) || agents.value[0])
}

function select(agent?: ProjectAgent) {
  selectedId.value = agent?.id || ''
  form.name = agent?.name || ''
  form.description = agent?.description || ''
  form.model = agent?.model || ''
  form.effort = agent?.effort || ''
  form.prompt_template_ids = { ...(agent?.prompt_template_ids || {}) }
  form.enabled = agent?.enabled ?? true
}

function setTemplate(phase: PromptPhase, id: string) {
  const next = { ...form.prompt_template_ids }
  if (id) next[phase] = id
  else delete next[phase]
  form.prompt_template_ids = next
}

const modelGroups = computed(() => {
  const groups = new Map<string, ModelInfo[]>()
  for (const model of models.value) {
    const label = `${model.provider} · ${model.scope === 'account' ? '我的 API' : '平台'}`
    groups.set(label, [...(groups.get(label) || []), model])
  }
  return Array.from(groups)
})

function modelLabel(reference: string | null) {
  if (!reference) return '继承项目模型'
  const model = models.value.find((item) => item.id === reference)
  return model ? `${model.provider} / ${model.name}` : '模型已不可用'
}

async function save() {
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      model: form.model || null,
      effort: form.effort || null,
      prompt_template_ids: form.prompt_template_ids,
      enabled: form.enabled,
    }
    const agent = selectedId.value
      ? await updateProjectAgent(projectId.value, selectedId.value, payload)
      : await createProjectAgent(projectId.value, {
          name: payload.name,
          description: payload.description,
          model: payload.model,
          effort: payload.effort,
          prompt_template_ids: payload.prompt_template_ids,
        })
    selectedId.value = agent.id
    await load()
  } finally {
    saving.value = false
  }
}

async function activate() {
  if (!selectedId.value) return
  await activateProjectAgent(projectId.value, selectedId.value)
  await projects.fetchProject(projectId.value)
}

async function remove() {
  if (!selectedId.value || !window.confirm('确认删除这个项目 Agent？')) return
  await deleteProjectAgent(projectId.value, selectedId.value)
  select()
  await load()
}

onMounted(async () => {
  await projects.fetchProject(projectId.value)
  await load()
})
</script>

<template>
  <AppLayout>
    <div class="mx-auto max-w-6xl space-y-5 py-6">
      <router-link :to="`/projects/${projectId}/settings`" class="inline-flex items-center gap-1 text-sm muse-text-muted">
        <ArrowLeft class="h-4 w-4" />返回项目设置
      </router-link>
      <div>
        <h1 class="text-xl font-semibold muse-text-heading">项目 Agents</h1>
        <p class="mt-1 text-sm muse-text-muted">项目绑定实际 Agent；模型、推理强度和账号模板会在 Run 创建时解析并冻结。</p>
      </div>
      <div class="grid gap-5 md:grid-cols-[300px_1fr]">
        <Card class="space-y-2 p-4">
          <Button v-if="canManage" class="w-full" variant="secondary" @click="select()"><Plus class="h-4 w-4" />新建 Agent</Button>
          <button
            v-for="item in agents"
            :key="item.id"
            type="button"
            class="w-full rounded-lg border p-3 text-left text-xs"
            :class="item.id === selectedId ? 'border-[color:var(--muse-accent)]' : 'border-[color:var(--muse-border)]'"
            @click="select(item)"
          >
            <span class="flex items-center gap-1 font-semibold muse-text-heading">
              <Check v-if="item.id === activeId" class="h-3.5 w-3.5" />{{ item.name }}
            </span>
            <span class="mt-1 block muse-text-faint">{{ modelLabel(item.model) }} · v{{ item.version }} · {{ item.enabled ? 'enabled' : 'disabled' }}</span>
          </button>
        </Card>
        <Card class="space-y-4 p-5">
          <input v-model="form.name" class="muse-input w-full" placeholder="Agent 名称" :disabled="!canManage" />
          <textarea v-model="form.description" class="muse-input min-h-20 w-full" placeholder="Agent 的职责与定位" :disabled="!canManage" />
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="text-xs muse-text-muted">模型
              <select v-model="form.model" class="muse-input mt-1 w-full" :disabled="!canManage">
                <option value="">继承项目运行模式模型</option>
                <optgroup v-for="[provider, providerModels] in modelGroups" :key="provider" :label="provider">
                  <option v-for="model in providerModels" :key="model.id" :value="model.id">{{ model.name }}</option>
                </optgroup>
              </select>
            </label>
            <label class="text-xs muse-text-muted">推理强度
              <select v-model="form.effort" class="muse-input mt-1 w-full" :disabled="!canManage">
                <option value="">模型默认</option><option value="low">低</option><option value="medium">中</option><option value="high">高</option>
              </select>
            </label>
          </div>
          <div class="space-y-3">
            <h2 class="text-sm font-semibold muse-text-heading">账号提示词模板绑定</h2>
            <label v-for="phase in phases" :key="phase" class="grid gap-2 text-xs sm:grid-cols-[120px_1fr] sm:items-center">
              <span>{{ phase }}</span>
              <select :value="form.prompt_template_ids[phase] || ''" class="muse-input" :disabled="!canManage" @change="setTemplate(phase, ($event.target as HTMLSelectElement).value)">
                <option value="">使用内置阶段提示词</option>
                <option v-for="template in templates.filter((item) => item.phase === phase)" :key="template.id" :value="template.id">{{ template.name }} · v{{ template.version }}</option>
              </select>
            </label>
          </div>
          <label v-if="selectedId" class="flex items-center gap-2 text-sm">
            <input v-model="form.enabled" type="checkbox" :disabled="!canManage || selectedId === activeId" />启用
          </label>
          <div v-if="canManage" class="flex flex-wrap justify-between gap-2">
            <Button v-if="selectedId && selectedId !== activeId" variant="danger" @click="remove"><Trash2 class="h-4 w-4" />删除</Button>
            <span v-else />
            <div class="flex gap-2">
              <Button v-if="selectedId && selectedId !== activeId && form.enabled" variant="secondary" @click="activate"><Check class="h-4 w-4" />设为活动 Agent</Button>
              <Button :loading="saving" :disabled="!form.name.trim()" @click="save"><Save class="h-4 w-4" />保存</Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>
