<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Textarea from '@/components/ui/Textarea.vue'
import { chatWithReport, getReport } from '@/api/report'
import { getInterviewHistory, interviewAgent } from '@/api/simulation'

const route = useRoute()
const router = useRouter()

const reportId = String(route.params.reportId || '')
const simulationId = ref('')
const question = ref('')
const answer = ref('')
const interviewPrompt = ref('请从你的立场给出下一步行动建议。')
const interviewResult = ref<any | null>(null)
const history = ref<any[]>([])
const loading = ref(false)
const chatting = ref(false)
const interviewing = ref(false)

async function loadData() {
  loading.value = true
  try {
    const report = await getReport(reportId)
    simulationId.value = String(report.simulation_id || '')
    if (simulationId.value) {
      history.value = await getInterviewHistory({ simulation_id: simulationId.value, limit: 50 })
    }
  } finally {
    loading.value = false
  }
}

async function handleAskReport() {
  if (!simulationId.value || !question.value.trim()) return
  chatting.value = true
  try {
    const result = await chatWithReport({
      simulation_id: simulationId.value,
      message: question.value.trim(),
    })
    answer.value = String(result.answer || '')
  } finally {
    chatting.value = false
  }
}

async function handleInterview() {
  if (!simulationId.value || !interviewPrompt.value.trim()) return
  interviewing.value = true
  try {
    interviewResult.value = await interviewAgent({
      simulation_id: simulationId.value,
      prompt: interviewPrompt.value.trim(),
    })
    history.value = await getInterviewHistory({ simulation_id: simulationId.value, limit: 50 })
  } finally {
    interviewing.value = false
  }
}

onMounted(() => {
  void loadData()
})
</script>

<template>
  <AppLayout>
    <div class="space-y-5">
      <Card>
        <div class="flex items-start justify-between gap-4">
          <div>
            <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">Report Interaction</h1>
            <p class="text-sm text-stone-500 dark:text-zinc-400">Report: {{ reportId }} · Simulation: {{ simulationId || '-' }}</p>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button variant="ghost" :loading="loading" @click="loadData">刷新</Button>
            <Button variant="ghost" @click="router.push(`/report/${reportId}`)">返回报告</Button>
          </div>
        </div>
      </Card>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider mb-2">Report Agent Chat</h2>
          <Textarea
            v-model="question"
            :rows="4"
            placeholder="输入你对报告的追问"
          />
          <div class="mt-2 flex justify-end">
            <Button :loading="chatting" @click="handleAskReport">提问</Button>
          </div>
          <pre class="mt-3 text-xs text-stone-700 dark:text-zinc-300 whitespace-pre-wrap max-h-72 overflow-y-auto">{{ answer || '暂无回答' }}</pre>
        </Card>

        <Card>
          <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider mb-2">Agent Interview</h2>
          <Textarea
            v-model="interviewPrompt"
            :rows="4"
            placeholder="输入采访问题"
          />
          <div class="mt-2 flex justify-end">
            <Button :loading="interviewing" @click="handleInterview">采访</Button>
          </div>
          <pre class="mt-3 text-xs text-stone-700 dark:text-zinc-300 whitespace-pre-wrap max-h-72 overflow-y-auto">{{ interviewResult || '暂无采访结果' }}</pre>
        </Card>
      </div>

      <Card>
        <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider mb-2">Interview History</h2>
        <div v-if="history.length === 0" class="text-sm text-stone-500 dark:text-zinc-500">暂无历史</div>
        <div v-else class="space-y-2 max-h-[28rem] overflow-y-auto">
          <div
            v-for="(item, idx) in history"
            :key="idx"
            class="rounded border border-stone-300 dark:border-zinc-700 bg-stone-100/70 dark:bg-zinc-800/40 p-2"
          >
            <p class="text-xs text-stone-500 dark:text-zinc-400">{{ item.agent }} · {{ item.created_at }}</p>
            <p class="mt-1 text-xs text-stone-600 dark:text-zinc-300">Q: {{ item.prompt }}</p>
            <p class="mt-1 text-xs text-stone-700 dark:text-zinc-200">A: {{ item.response }}</p>
          </div>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>
