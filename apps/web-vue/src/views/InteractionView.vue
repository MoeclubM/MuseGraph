<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Textarea from '@/components/ui/Textarea.vue'
import { chatWithReport, getReport } from '@/api/report'

const route = useRoute()
const router = useRouter()

const reportId = String(route.params.reportId || '')
const simulationId = ref('')
const question = ref('')
const answer = ref('')
const loading = ref(false)
const chatting = ref(false)

async function loadData() {
  loading.value = true
  try {
    const report = await getReport(reportId)
    simulationId.value = String(report.simulation_id || '')
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

onMounted(() => {
  void loadData()
})
</script>

<template>
  <AppLayout>
    <div class="muse-page-shell muse-page-shell-wide">
      <section class="muse-page-header">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">Report Discussion</h1>
            <p class="text-sm text-stone-500 dark:text-zinc-400">Report: {{ reportId }} · Analysis Session: {{ simulationId || '-' }}</p>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button variant="ghost" :loading="loading" @click="loadData">Refresh</Button>
            <Button variant="ghost" @click="router.push(`/report/${reportId}`)">Open Report</Button>
          </div>
        </div>
      </section>

      <Card>
        <h2 class="mb-2 text-sm font-medium uppercase tracking-wider text-stone-600 dark:text-zinc-300">Report Q&amp;A</h2>
        <Textarea
          v-model="question"
          :rows="5"
          placeholder="Ask a follow-up question about the report, reasoning process, or next steps"
        />
        <div class="mt-2 flex justify-end">
          <Button :loading="chatting" @click="handleAskReport">Ask</Button>
        </div>
        <pre class="mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap text-xs text-stone-700 dark:text-zinc-300">{{ answer || 'No answer yet.' }}</pre>
      </Card>
    </div>
  </AppLayout>
</template>
