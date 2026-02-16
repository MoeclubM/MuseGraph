<script setup lang="ts">
import { ref } from 'vue'
import { Search, Loader2 } from 'lucide-vue-next'
import { searchGraph } from '@/api/graph'

const props = defineProps<{
  projectId: string
}>()

const query = ref('')
const searchType = ref('INSIGHTS')
const results = ref<any[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const hasSearched = ref(false)

const searchTypes = [
  { value: 'INSIGHTS', label: 'Insights' },
  { value: 'GRAPH_COMPLETION', label: 'Graph AI' },
  { value: 'RAG_COMPLETION', label: 'RAG' },
  { value: 'SUMMARIES', label: 'Summaries' },
  { value: 'CHUNKS', label: 'Chunks' },
  { value: 'GRAPH_SUMMARY_COMPLETION', label: 'Graph Summary' },
]

function extractText(result: any): string {
  if (typeof result === 'object' && result !== null) {
    return result.content || result.text || JSON.stringify(result, null, 2)
  }
  const s = String(result)
  // Parse Python dict string format: {'text': '...'}
  const m = s.match(/'text'\s*:\s*'([^']*(?:''[^']*)*)'/)
  if (m) return m[1].replace(/''/g, "'")
  return s
}

async function handleSearch() {
  if (!query.value.trim()) return
  loading.value = true
  error.value = null
  hasSearched.value = true
  try {
    results.value = await searchGraph(props.projectId, query.value, searchType.value)
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || e.message || 'Search failed'
    results.value = []
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex gap-2">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
        <input
          v-model="query"
          type="text"
          placeholder="Search knowledge graph..."
          class="w-full rounded-lg border border-slate-700 bg-slate-800 pl-9 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          @keydown.enter="handleSearch"
        />
      </div>
      <select
        v-model="searchType"
        class="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-blue-500 focus:outline-none"
      >
        <option v-for="st in searchTypes" :key="st.value" :value="st.value">
          {{ st.label }}
        </option>
      </select>
      <button
        class="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
        :disabled="loading || !query.trim()"
        @click="handleSearch"
      >
        <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
        <span v-else>Search</span>
      </button>
    </div>

    <div v-if="error" class="rounded-lg bg-red-900/30 border border-red-800 px-3 py-2 text-sm text-red-300">
      {{ error }}
    </div>

    <div v-if="hasSearched && !loading && results.length === 0 && !error" class="text-center py-6">
      <p class="text-sm text-slate-500">No results found</p>
    </div>

    <div v-if="results.length > 0" class="space-y-2 max-h-80 overflow-y-auto">
      <div
        v-for="(result, idx) in results"
        :key="idx"
        class="rounded-lg border border-slate-700/50 bg-slate-800/50 p-3"
      >
        <p class="text-sm text-slate-200 whitespace-pre-wrap">
          {{ extractText(result) }}
        </p>
        <div v-if="result.score" class="mt-1">
          <span class="text-xs text-slate-500">Score: {{ result.score.toFixed(3) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
