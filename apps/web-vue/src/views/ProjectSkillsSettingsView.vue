<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Download, Loader2, Plus, Trash2, Upload } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import { useToast } from '@/composables/useToast'
import {
  createSkill,
  deleteSkill,
  listSkills,
  toggleSkill,
  type SkillCreatePayload,
  type SkillItem,
} from '@/api/skills'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const toast = useToast()

const projectId = computed(() => String(route.params.id || ''))
const loading = ref(true)
const skills = ref<SkillItem[]>([])
// Local mirror of "explicitly disabled" slugs. The backend GET hides
// disabled built-ins, so to render their toggle as off we keep a local set
// updated by toggle responses. Refresh on mount only fetches enabled ones.
const disabledLocally = ref<Set<string>>(new Set())

const builtins = computed<SkillItem[]>(() =>
  skills.value.filter((s) => s.is_builtin).sort((a, b) => a.slug.localeCompare(b.slug)),
)
const customs = computed<SkillItem[]>(() =>
  skills.value.filter((s) => !s.is_builtin).sort((a, b) => a.slug.localeCompare(b.slug)),
)

async function refresh() {
  if (!projectId.value) return
  loading.value = true
  try {
    skills.value = await listSkills(projectId.value, 'chat')
  } catch (err) {
    toast.error(t('projectSkills.loadError', '加载 skills 失败'))
  } finally {
    loading.value = false
  }
}

watch(projectId, refresh)
onMounted(refresh)

async function onToggleBuiltin(slug: string, enabled: boolean) {
  try {
    await toggleSkill(projectId.value, slug, enabled)
    if (enabled) disabledLocally.value.delete(slug)
    else disabledLocally.value.add(slug)
    await refresh()
  } catch {
    toast.error(t('projectSkills.toggleError', '切换 skill 失败'))
  }
}

const showCreate = ref(false)
const form = reactive<SkillCreatePayload>({
  slug: '',
  name: '',
  description: '',
  system_prompt: '',
  scope: ['chat'],
})
const creating = ref(false)
function resetForm() {
  form.slug = ''
  form.name = ''
  form.description = ''
  form.system_prompt = ''
  form.scope = ['chat']
}

async function onCreate() {
  if (!form.slug.trim() || !form.name.trim() || !form.system_prompt.trim()) {
    toast.error(t('projectSkills.requiredFields', '请填写 slug、name 与 system_prompt'))
    return
  }
  creating.value = true
  try {
    await createSkill(projectId.value, { ...form })
    showCreate.value = false
    resetForm()
    await refresh()
    toast.success(t('projectSkills.created', '已创建自定义 skill'))
  } catch (err: any) {
    toast.error(err?.response?.data?.detail || t('projectSkills.createError', '创建失败'))
  } finally {
    creating.value = false
  }
}

async function onDeleteCustom(slug: string) {
  if (!window.confirm(t('projectSkills.confirmDelete', '确认删除该自定义 skill？'))) return
  try {
    await deleteSkill(projectId.value, slug)
    await refresh()
  } catch {
    toast.error(t('projectSkills.deleteError', '删除失败'))
  }
}

function backToSettings() {
  router.push({ name: 'project-settings', params: { id: projectId.value } })
}

// --- Import / Export ---
const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)

function triggerImport() {
  fileInput.value?.click()
}

async function handleFileImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importing.value = true
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    if (!data.slug || !data.name || !data.system_prompt) {
      toast.error('Skill 文件格式错误：需要 slug、name、system_prompt 字段')
      return
    }
    await createSkill(projectId.value, {
      slug: data.slug,
      name: data.name,
      description: data.description || '',
      system_prompt: data.system_prompt,
      scope: data.scope || ['chat'],
      tags: data.tags || [],
      icon: data.icon || 'sparkles',
      allowed_tools: data.allowed_tools || null,
      default_model_component: data.default_model_component || null,
    })
    await refresh()
    toast.success(`已导入 skill @${data.slug}`)
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err.message || '导入失败'
    toast.error(msg)
  } finally {
    importing.value = false
    input.value = '' // reset so same file can be re-imported
  }
}

function exportSkill(s: SkillItem) {
  const blob = new Blob([JSON.stringify({
    slug: s.slug,
    name: s.name,
    icon: s.icon,
    description: s.description,
    scope: s.scope,
    tags: s.tags,
    system_prompt: s.system_prompt,
    allowed_tools: s.allowed_tools,
    default_model_component: s.default_model_component,
  }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${s.slug}.skill.json`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <AppLayout>
    <div class="mx-auto w-full max-w-3xl space-y-4 p-4">
      <header class="flex items-center gap-2">
        <Button variant="ghost" size="sm" @click="backToSettings">
          <ArrowLeft class="h-4 w-4" />
          {{ t('common.back', '返回') }}
        </Button>
        <h1 class="text-lg font-semibold">{{ t('projectSkills.title', '项目 Skills') }}</h1>
      </header>

      <Card>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-medium">
              {{ t('projectSkills.builtinSection', '系统预置 skill（可开关）') }}
            </h2>
            <span v-if="loading" class="muse-text-muted text-xs">
              <Loader2 class="inline h-3 w-3 animate-spin" />
              {{ t('common.loading', '加载中') }}
            </span>
          </div>
        </template>

        <ul class="divide-y">
          <li
            v-for="s in builtins"
            :key="s.slug"
            class="flex items-start gap-3 py-2"
          >
            <Checkbox
              :model-value="!disabledLocally.has(s.slug)"
              @update:model-value="(v: boolean) => onToggleBuiltin(s.slug, v)"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <code class="text-xs font-semibold text-[color:var(--muse-accent)]">@{{ s.slug }}</code>
                <span class="text-sm font-medium">{{ s.name }}</span>
              </div>
              <p class="muse-text-muted text-xs">{{ s.description }}</p>
              <div class="mt-1 flex flex-wrap gap-1">
                <span
                  v-for="tag in s.tags"
                  :key="tag"
                  class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] muse-text-muted"
                >{{ tag }}</span>
              </div>
            </div>
          </li>
          <li v-if="!loading && !builtins.length" class="muse-text-muted py-4 text-sm">
            {{ t('projectSkills.empty', '暂无内置 skill') }}
          </li>
        </ul>
      </Card>

      <Card>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-medium">
              {{ t('projectSkills.customSection', '项目自定义') }}
            </h2>
            <div class="flex gap-2">
              <Button size="sm" variant="secondary" :disabled="importing" @click="triggerImport">
                <Upload v-if="!importing" class="h-3 w-3" />
                <Loader2 v-else class="h-3 w-3 animate-spin" />
                {{ t('projectSkills.import', '导入') }}
              </Button>
              <input
                ref="fileInput"
                type="file"
                accept=".json,.skill.json"
                class="hidden"
                @change="handleFileImport"
              />
              <Button size="sm" @click="showCreate = !showCreate">
                <Plus class="h-3 w-3" />
                {{ t('projectSkills.add', '新增') }}
              </Button>
            </div>
          </div>
        </template>

        <div v-if="showCreate" class="mb-4 space-y-2 rounded border p-3">
          <Input v-model="form.slug" :placeholder="t('projectSkills.slugPh', 'slug (英文/数字/-_)')" />
          <Input v-model="form.name" :placeholder="t('projectSkills.namePh', '显示名称')" />
          <Input v-model="form.description" :placeholder="t('projectSkills.descPh', '一句话描述')" />
          <textarea
            v-model="form.system_prompt"
            rows="6"
            class="muse-input min-h-[120px] w-full"
            :placeholder="t('projectSkills.promptPh', 'system prompt — 该 skill 激活后追加到 orchestrator 系统提示')"
          />
          <div class="flex gap-2">
            <Button size="sm" :disabled="creating" @click="onCreate">
              <Loader2 v-if="creating" class="h-3 w-3 animate-spin" />
              {{ t('projectSkills.create', '创建') }}
            </Button>
            <Button size="sm" variant="ghost" @click="(showCreate = false), resetForm()">
              {{ t('common.cancel', '取消') }}
            </Button>
          </div>
        </div>

        <ul class="divide-y">
          <li
            v-for="s in customs"
            :key="s.slug"
            class="flex items-center gap-3 py-2"
          >
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <code class="text-xs font-semibold text-[color:var(--muse-accent)]">@{{ s.slug }}</code>
                <span class="text-sm font-medium">{{ s.name }}</span>
              </div>
              <p class="muse-text-muted text-xs">{{ s.description }}</p>
            </div>
            <div class="flex gap-1">
              <Button variant="ghost" size="sm" :title="t('projectSkills.export', '导出')" @click="exportSkill(s)">
                <Download class="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" @click="onDeleteCustom(s.slug)">
                <Trash2 class="h-4 w-4" />
              </Button>
            </div>
          </li>
          <li v-if="!loading && !customs.length" class="muse-text-muted py-4 text-sm">
            {{ t('projectSkills.noCustom', '暂无自定义 skill') }}
          </li>
        </ul>
      </Card>
    </div>
  </AppLayout>
</template>
