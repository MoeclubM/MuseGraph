<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ArrowLeft, Plus, Save, Trash2 } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Button from '@/components/ui/Button.vue'
import Card from '@/components/ui/Card.vue'
import {
  createPromptTemplate,
  deletePromptTemplate,
  listPromptTemplates,
  updatePromptTemplate,
} from '@/api/agentConfiguration'
import type { PromptPhase, PromptTemplate } from '@/types'

const phases: PromptPhase[] = ['architect', 'planner', 'writer', 'auditor', 'reviser']
const templates = ref<PromptTemplate[]>([])
const selectedId = ref('')
const saving = ref(false)
const form = reactive({
  name: '',
  description: '',
  phase: 'architect' as PromptPhase,
  content: '',
})

async function load() {
  templates.value = await listPromptTemplates()
  if (selectedId.value) select(templates.value.find((item) => item.id === selectedId.value))
}

function select(template?: PromptTemplate) {
  selectedId.value = template?.id || ''
  form.name = template?.name || ''
  form.description = template?.description || ''
  form.phase = template?.phase || 'architect'
  form.content = template?.content || ''
}

async function save() {
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      phase: form.phase,
      content: form.content,
    }
    const template = selectedId.value
      ? await updatePromptTemplate(selectedId.value, payload)
      : await createPromptTemplate(payload)
    selectedId.value = template.id
    await load()
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!selectedId.value || !window.confirm('确认删除这个提示词模板？')) return
  await deletePromptTemplate(selectedId.value)
  select()
  await load()
}

onMounted(load)
</script>

<template>
  <AppLayout>
    <div class="mx-auto max-w-5xl space-y-5 py-6">
      <router-link to="/settings" class="inline-flex items-center gap-1 text-sm muse-text-muted">
        <ArrowLeft class="h-4 w-4" />返回账号设置
      </router-link>
      <div>
        <h1 class="text-xl font-semibold muse-text-heading">账号提示词模板</h1>
        <p class="mt-1 text-sm muse-text-muted">模板属于当前账号；绑定到项目 Agent 后，每次 Run 会冻结模板内容与版本。</p>
      </div>
      <div class="grid gap-5 md:grid-cols-[280px_1fr]">
        <Card class="space-y-2 p-4">
          <Button class="w-full" variant="secondary" @click="select()"><Plus class="h-4 w-4" />新建模板</Button>
          <button
            v-for="template in templates"
            :key="template.id"
            type="button"
            class="w-full rounded-lg border p-3 text-left text-xs"
            :class="template.id === selectedId ? 'border-[color:var(--muse-accent)]' : 'border-[color:var(--muse-border)]'"
            @click="select(template)"
          >
            <span class="block font-semibold muse-text-heading">{{ template.name }}</span>
            <span class="mt-1 block muse-text-faint">{{ template.phase }} · v{{ template.version }}</span>
          </button>
        </Card>
        <Card class="space-y-4 p-5">
          <input v-model="form.name" class="muse-input w-full" placeholder="模板名称" />
          <input v-model="form.description" class="muse-input w-full" placeholder="用途说明" />
          <select v-model="form.phase" class="muse-input w-full">
            <option v-for="phase in phases" :key="phase" :value="phase">{{ phase }}</option>
          </select>
          <textarea
            v-model="form.content"
            class="muse-input min-h-72 w-full font-mono text-xs"
            placeholder="阶段提示词。可使用 {{instruction}}、{{project_title}}、{{project_description}}、{{pack_slug}}、{{agent_name}}。"
          />
          <div class="flex justify-between">
            <Button v-if="selectedId" variant="danger" @click="remove"><Trash2 class="h-4 w-4" />删除</Button>
            <span v-else />
            <Button :loading="saving" :disabled="!form.name.trim() || !form.content.trim()" @click="save">
              <Save class="h-4 w-4" />保存
            </Button>
          </div>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>
