<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Check, Loader2, SendHorizontal, Square, X } from '@lucide/vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { listProjectFiles, type ProjectFile } from '@/api/projectFiles'
import { listSkills, type SkillItem } from '@/api/skills'
import { listProjectAgents } from '@/api/agentConfiguration'
import { useAgentStore } from '@/stores/agent'
import { useProjectStore } from '@/stores/project'
import type { AgentRunMode, ProjectAgent } from '@/types'

const props = defineProps<{ projectId: string }>()
const agent = useAgentStore()
const projects = useProjectStore()
const instruction = ref('')
const mode = ref<AgentRunMode>('write')
const skillSlug = ref('')
const selectedAgentId = ref('')
const files = ref<ProjectFile[]>([])
const skills = ref<SkillItem[]>([])
const projectAgents = ref<ProjectAgent[]>([])
const targetRefs = ref<string[]>([])

const availableSkills = computed(() => skills.value.filter((skill) => skill.scopes.includes(mode.value)))
const finalSummary = computed(() => String(agent.currentRun?.final_output?.summary || ''))
const usedKnowledgeIds = computed(() => agent.currentRun?.final_output?.used_knowledge_ids || [])
const usedPlanUnitIds = computed(() => agent.currentRun?.final_output?.used_plan_unit_ids || [])
const creativeUnits = computed(() => {
  const plan = agent.currentRun?.creative_plan as { units?: Record<string, unknown>[] } | null
  return plan?.units || []
})

async function loadSelectors() {
  const [projectFiles, projectSkills, agents, project] = await Promise.all([
    listProjectFiles(props.projectId),
    listSkills(props.projectId),
    listProjectAgents(props.projectId),
    projects.fetchProject(props.projectId),
  ])
  files.value = projectFiles
  skills.value = projectSkills
  projectAgents.value = agents
  selectedAgentId.value = project.active_agent_id
    || agents.find((item) => item.enabled)?.id
    || ''
}

async function submit() {
  const value = instruction.value.trim()
  if (!value) return
  await agent.startRun(props.projectId, value, {
    mode: mode.value,
    agent_id: selectedAgentId.value,
    skill_slug: skillSlug.value || null,
    target_refs: targetRefs.value,
  })
  instruction.value = ''
}

function toggleTarget(path: string) {
  targetRefs.value = targetRefs.value.includes(path)
    ? targetRefs.value.filter((item) => item !== path)
    : [...targetRefs.value, path]
}

onMounted(loadSelectors)
watch(() => props.projectId, loadSelectors)
watch(mode, () => {
  if (!availableSkills.value.some((skill) => skill.slug === skillSlug.value)) skillSlug.value = ''
})
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col bg-[color:var(--muse-surface)]">
    <header class="border-b border-[color:var(--muse-border)] px-5 py-3">
      <div v-if="agent.currentRun" class="flex items-center gap-3">
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-semibold muse-text-heading">{{ agent.currentRun.instruction }}</p>
          <p class="text-xs muse-text-faint">
            {{ agent.currentRun.mode }} · {{ agent.currentRun.status }} ·
            {{ String(agent.currentRun.agent_snapshot?.name || 'Agent') }} ·
            {{ String(agent.currentRun.skill_snapshot?.slug || 'general') }}
          </p>
        </div>
        <button
          v-if="agent.isRunActive"
          class="muse-btn muse-btn-secondary"
          type="button"
          @click="agent.cancelCurrent(props.projectId)"
        >
          <Square class="h-3.5 w-3.5" />
          取消
        </button>
      </div>
      <p v-else class="text-sm font-semibold muse-text-heading">创建新的文本创作运行</p>
    </header>

    <section v-if="agent.currentRun" class="min-h-0 flex-1 overflow-y-auto p-5">
      <div class="mx-auto max-w-4xl space-y-5">
        <div v-if="agent.events.length" class="muse-panel p-4">
          <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide muse-text-faint">运行事件</h3>
          <ol class="space-y-2">
            <li v-for="event in agent.events" :key="event.id" class="flex gap-3 text-xs">
              <span class="w-7 shrink-0 muse-text-faint">#{{ event.id }}</span>
              <span class="w-32 shrink-0 font-medium muse-text-body">{{ event.event }}</span>
              <span class="break-all muse-text-muted">{{ JSON.stringify(event.data) }}</span>
            </li>
          </ol>
        </div>

        <div v-if="agent.currentRun.error" class="rounded-lg border border-red-400/40 bg-red-500/10 p-4 text-sm text-red-600">
          {{ agent.currentRun.error }}
        </div>

        <div v-if="finalSummary" class="muse-panel p-5">
          <h3 class="mb-3 text-sm font-semibold muse-text-heading">Agent 结果</h3>
          <MarkdownRenderer :text="finalSummary" />
          <div v-if="usedKnowledgeIds.length" class="mt-4">
            <p class="mb-2 text-xs font-semibold muse-text-faint">已使用的知识 ID</p>
            <div class="flex flex-wrap gap-2">
              <code v-for="id in usedKnowledgeIds" :key="id" class="rounded bg-[color:var(--muse-surface-muted)] px-2 py-1 text-xs">{{ id }}</code>
            </div>
          </div>
          <div v-if="usedPlanUnitIds.length" class="mt-4">
            <p class="mb-2 text-xs font-semibold muse-text-faint">已落实的蓝图单元</p>
            <div class="flex flex-wrap gap-2">
              <code v-for="id in usedPlanUnitIds" :key="id" class="rounded bg-[color:var(--muse-surface-muted)] px-2 py-1 text-xs">{{ id }}</code>
            </div>
          </div>
        </div>

        <div v-if="creativeUnits.length" class="muse-panel p-5">
          <h3 class="mb-3 text-sm font-semibold muse-text-heading">创作蓝图</h3>
          <ol class="space-y-3">
            <li v-for="unit in creativeUnits" :key="String(unit.id)" class="rounded border border-[color:var(--muse-border)] p-3 text-xs">
              <p class="font-semibold muse-text-heading">{{ unit.id }} · {{ unit.title }}</p>
              <p class="mt-1 muse-text-body">{{ unit.purpose }}</p>
              <p class="mt-1 muse-text-muted">{{ unit.summary }}</p>
              <p class="mt-2 muse-text-faint">依赖：{{ (unit.depends_on_ids as string[])?.join(', ') || '无' }} · 输出：{{ unit.target_ref || '无' }}</p>
            </li>
          </ol>
        </div>

        <div v-if="agent.changeSet" class="space-y-4">
          <div v-for="file in agent.changeSet.files" :key="file.path" class="muse-panel overflow-hidden">
            <div class="flex items-center justify-between border-b border-[color:var(--muse-border)] px-4 py-2">
              <span class="text-sm font-medium muse-text-heading">{{ file.path }}</span>
              <span class="text-xs muse-text-faint">{{ file.change_type }}</span>
            </div>
            <pre class="max-h-[34rem] overflow-auto whitespace-pre-wrap p-4 text-xs leading-5">{{ file.diff }}</pre>
          </div>

          <div v-if="agent.changeSet.knowledge.length" class="muse-panel p-4">
            <h3 class="mb-3 text-sm font-semibold muse-text-heading">结构化知识变更</h3>
            <div v-for="(operation, index) in agent.changeSet.knowledge" :key="index" class="mb-3 rounded border border-[color:var(--muse-border)] p-3 text-xs">
              <p class="font-semibold">{{ operation.operation }} · {{ operation.record?.id || operation.record_id }}</p>
              <pre class="mt-2 overflow-auto whitespace-pre-wrap">{{ JSON.stringify(operation.record || {}, null, 2) }}</pre>
            </div>
          </div>

          <div v-if="agent.changeSet.self_review" class="muse-panel p-4">
            <h3 class="text-sm font-semibold muse-text-heading">自检报告</h3>
            <p class="mt-2 text-sm muse-text-body">{{ agent.changeSet.self_review.summary }}</p>
            <pre class="mt-3 overflow-auto whitespace-pre-wrap text-xs">{{ JSON.stringify(agent.changeSet.validation, null, 2) }}</pre>
          </div>
        </div>

        <div v-if="agent.isAwaitingReview" class="sticky bottom-0 flex justify-end gap-3 rounded-xl border border-[color:var(--muse-border)] bg-[color:var(--muse-surface)]/95 p-4 shadow-lg backdrop-blur">
          <button class="muse-btn muse-btn-secondary" type="button" :disabled="agent.submitting" @click="agent.reviewCurrent(props.projectId, 'reject')">
            <X class="h-4 w-4" />
            整轮拒绝
          </button>
          <button class="muse-btn muse-btn-primary" type="button" :disabled="agent.submitting" @click="agent.reviewCurrent(props.projectId, 'accept')">
            <Check class="h-4 w-4" />
            接受并发布
          </button>
        </div>
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-y-auto p-6">
      <div class="mx-auto max-w-3xl space-y-5">
        <textarea
          v-model="instruction"
          class="muse-input min-h-44 w-full resize-y p-4 text-sm"
          placeholder="描述目标、交付文件和必须使用的事实或约束……"
        />
        <div class="grid gap-4 sm:grid-cols-3">
          <label class="text-xs muse-text-muted">
            模式
            <select v-model="mode" class="muse-input mt-1 w-full">
              <option value="write">创作</option>
              <option value="analyze">分析</option>
              <option value="suggest">建议</option>
            </select>
          </label>
          <label class="text-xs muse-text-muted">
            Skill
            <select v-model="skillSlug" class="muse-input mt-1 w-full">
              <option value="">按 Pack 自动选择</option>
              <option v-for="skill in availableSkills" :key="skill.slug" :value="skill.slug">{{ skill.name }}</option>
            </select>
          </label>
          <label class="text-xs muse-text-muted">
            项目 Agent
            <select v-model="selectedAgentId" class="muse-input mt-1 w-full">
              <option v-for="item in projectAgents.filter((value) => value.enabled)" :key="item.id" :value="item.id">
                {{ item.name }} · {{ item.model || '继承项目模型' }}
              </option>
            </select>
          </label>
        </div>

        <div>
          <p class="mb-2 text-xs font-semibold muse-text-faint">限定目标文件（不选则由 Agent 根据控制文档决定）</p>
          <div class="max-h-48 overflow-auto rounded-lg border border-[color:var(--muse-border)] p-2">
            <label v-for="file in files" :key="file.path" class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-[color:var(--muse-surface-muted)]">
              <input type="checkbox" :checked="targetRefs.includes(file.path)" @change="toggleTarget(file.path)" />
              <span class="truncate">{{ file.path }}</span>
            </label>
          </div>
        </div>

        <div class="flex justify-end">
          <button class="muse-btn muse-btn-primary" type="button" :disabled="agent.submitting || !instruction.trim() || !selectedAgentId" @click="submit">
            <Loader2 v-if="agent.submitting" class="h-4 w-4 animate-spin" />
            <SendHorizontal v-else class="h-4 w-4" />
            开始运行
          </button>
        </div>
      </div>
    </section>
  </main>
</template>
