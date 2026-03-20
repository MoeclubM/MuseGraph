<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { getReport, getReportSections } from '@/api/report'

const route = useRoute()
const router = useRouter()

const reportId = String(route.params.reportId || '')
const report = ref<any | null>(null)
const sections = ref<any[]>([])
const loading = ref(false)

async function loadData() {
  if (!reportId) return
  loading.value = true
  try {
    report.value = await getReport(reportId)
    const sectionData = await getReportSections(reportId)
    sections.value = sectionData.sections || []
  } finally {
    loading.value = false
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
            <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">{{ report?.title || 'OASIS Report' }}</h1>
            <p class="text-sm text-stone-500 dark:text-zinc-400">
              Report ID: {{ reportId }} · Simulation: {{ report?.simulation_id || '-' }}
            </p>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button variant="ghost" :loading="loading" @click="loadData">Refresh</Button>
            <Button
              v-if="report?.simulation_id"
              variant="secondary"
              @click="router.push(`/interaction/${reportId}`)"
            >
              Open Interaction
            </Button>
            <Button
              v-if="report?.simulation_id"
              variant="ghost"
              @click="router.push(`/simulation/${report.simulation_id}`)"
            >
              Back to Simulation
            </Button>
          </div>
        </div>
      </section>

      <Card>
        <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider mb-2">Executive Summary</h2>
        <p class="text-sm text-stone-700 dark:text-zinc-200 whitespace-pre-wrap">
          {{ report?.executive_summary || 'No summary' }}
        </p>
      </Card>

      <Card>
        <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider mb-2">Sections</h2>
        <div v-if="sections.length === 0" class="text-sm text-stone-500 dark:text-zinc-500">No sections yet</div>
        <div v-else class="space-y-3">
          <div v-for="section in sections" :key="section.index" class="rounded border border-stone-300 dark:border-zinc-700 bg-stone-100/70 dark:bg-zinc-800/40 p-3">
            <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">{{ section.index + 1 }}. {{ section.title }}</h3>
            <p class="mt-1 text-xs text-stone-500 dark:text-zinc-400 whitespace-pre-wrap">{{ section.content }}</p>
          </div>
        </div>
      </Card>

      <Card>
        <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider mb-2">Markdown</h2>
        <pre class="text-xs text-stone-700 dark:text-zinc-300 whitespace-pre-wrap max-h-[32rem] overflow-y-auto">{{ report?.markdown || '' }}</pre>
      </Card>
    </div>
  </AppLayout>
</template>
