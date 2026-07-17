<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Loader2, Plus, Save, Trash2 } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import {
  createSkill,
  deleteSkill,
  listSkills,
  previewSkill,
  updateSkill,
  type SkillItem,
  type SkillWritePayload,
} from '@/api/skills'
import type { AgentRunMode, ResolvedSkill } from '@/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id || ''))
const skills = ref<SkillItem[]>([])
const loading = ref(false)
const saving = ref(false)
const editingSlug = ref('')
const preview = ref<ResolvedSkill | null>(null)
const form = reactive<SkillWritePayload>({
  slug: '',
  name: '',
  description: '',
  instructions: '',
  scopes: ['write'],
  roles: ['writer', 'auditor', 'reviser'],
  allowed_tools: ['list_files', 'read_file', 'knowledge_search', 'knowledge_get', 'write_file'],
  params_schema: { type: 'object', properties: {} },
  default_model_component: null,
  enabled: true,
})

const builtins = computed(() => skills.value.filter((skill) => skill.source === 'builtin'))
const customs = computed(() => skills.value.filter((skill) => skill.source === 'project'))

async function load() {
  loading.value = true
  try {
    skills.value = await listSkills(projectId.value)
  } finally {
    loading.value = false
  }
}

function edit(skill?: SkillItem) {
  editingSlug.value = skill?.slug || ''
  form.slug = skill?.slug || ''
  form.name = skill?.name || ''
  form.description = skill?.description || ''
  form.instructions = skill?.instructions || ''
  form.scopes = [...(skill?.scopes || ['write'])]
  form.roles = [...(skill?.roles || ['writer', 'auditor', 'reviser'])]
  form.allowed_tools = [...(skill?.allowed_tools || ['list_files', 'read_file', 'write_file'])]
  form.params_schema = { ...(skill?.params_schema || { type: 'object', properties: {} }) }
  form.default_model_component = skill?.default_model_component || null
  form.enabled = true
}

async function save() {
  saving.value = true
  try {
    if (editingSlug.value) {
      const { slug: _slug, ...payload } = form
      await updateSkill(projectId.value, editingSlug.value, payload)
    } else {
      await createSkill(projectId.value, { ...form })
    }
    await load()
    edit()
  } finally {
    saving.value = false
  }
}

async function remove(slug: string) {
  await deleteSkill(projectId.value, slug)
  await load()
  if (editingSlug.value === slug) edit()
}

async function resolvePreview(operation: AgentRunMode) {
  const role = operation === 'analyze' ? 'auditor' : 'writer'
  preview.value = await previewSkill(projectId.value, operation, role, form.slug || null)
}

watch(projectId, load, { immediate: true })
</script>

<template>
  <AppLayout>
    <div class="mx-auto max-w-5xl space-y-5 py-6">
      <router-link :to="`/projects/${projectId}/settings`" class="inline-flex items-center gap-1 text-sm muse-text-muted">
        <ArrowLeft class="h-4 w-4" />返回项目设置
      </router-link>
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold muse-text-heading">项目 Skills</h1>
          <p class="mt-1 text-sm muse-text-muted">内置 Skill 来自代码；自定义 Skill 只在当前项目内生效。</p>
        </div>
        <Button @click="edit()"><Plus class="mr-1 h-4 w-4" />新建</Button>
      </div>
      <div v-if="loading" class="flex justify-center py-16"><Loader2 class="h-5 w-5 animate-spin" /></div>
      <div v-else class="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div class="space-y-4">
          <Card class="p-4">
            <h2 class="mb-3 text-sm font-semibold">内置</h2>
            <div v-for="skill in builtins" :key="skill.slug" class="mb-3">
              <p class="text-xs font-semibold">@{{ skill.slug }} · {{ skill.name }}</p>
              <p class="mt-1 text-xs muse-text-faint">{{ skill.description }}</p>
            </div>
          </Card>
          <Card class="p-4">
            <h2 class="mb-3 text-sm font-semibold">当前项目</h2>
            <button v-for="skill in customs" :key="skill.slug" class="mb-2 block w-full rounded border border-[color:var(--muse-border)] p-2 text-left" @click="edit(skill)">
              <span class="text-xs font-semibold">@{{ skill.slug }} · {{ skill.name }}</span>
            </button>
          </Card>
        </div>
        <Card class="space-y-4 p-5">
          <h2 class="text-sm font-semibold">{{ editingSlug ? `编辑 @${editingSlug}` : '新建项目 Skill' }}</h2>
          <div class="grid gap-3 sm:grid-cols-2">
            <input v-model="form.slug" class="muse-input" placeholder="slug" :disabled="!!editingSlug" />
            <input v-model="form.name" class="muse-input" placeholder="名称" />
          </div>
          <input v-model="form.description" class="muse-input w-full" placeholder="说明" />
          <textarea v-model="form.instructions" class="muse-input min-h-40 w-full" placeholder="运行指令" />
          <label class="block text-xs muse-text-muted">Scopes（逗号分隔）
            <input :value="form.scopes.join(',')" class="muse-input mt-1 w-full" @input="form.scopes = (($event.target as HTMLInputElement).value.split(',').map((v) => v.trim()).filter(Boolean) as AgentRunMode[])" />
          </label>
          <label class="block text-xs muse-text-muted">Roles（逗号分隔）
            <input :value="form.roles.join(',')" class="muse-input mt-1 w-full" @input="form.roles = ($event.target as HTMLInputElement).value.split(',').map((v) => v.trim()).filter(Boolean)" />
          </label>
          <label class="block text-xs muse-text-muted">Allowed tools（逗号分隔）
            <input :value="form.allowed_tools.join(',')" class="muse-input mt-1 w-full" @input="form.allowed_tools = ($event.target as HTMLInputElement).value.split(',').map((v) => v.trim()).filter(Boolean)" />
          </label>
          <div class="flex flex-wrap gap-2">
            <Button :loading="saving" :disabled="!form.slug || !form.name || !form.instructions" @click="save"><Save class="mr-1 h-4 w-4" />保存</Button>
            <Button v-if="editingSlug" variant="danger" @click="remove(editingSlug)"><Trash2 class="mr-1 h-4 w-4" />删除</Button>
            <Button variant="secondary" @click="resolvePreview('write')">预览解析</Button>
          </div>
          <pre v-if="preview" class="max-h-72 overflow-auto rounded bg-[color:var(--muse-surface-muted)] p-3 text-xs">{{ JSON.stringify(preview, null, 2) }}</pre>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>
