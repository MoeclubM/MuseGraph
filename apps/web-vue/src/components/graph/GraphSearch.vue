<script setup lang="ts">
import { ref } from 'vue'
import { Search } from 'lucide-vue-next'
import { searchGraph } from '@/api/graph'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'

const props = defineProps<{
  projectId: string
}>()

const query = ref('')
const searchType = ref('INSIGHTS')
const results = ref<any[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const hasSearched = ref(false)
const useReranker = ref(false)
const rerankerTopN = ref<number>(6)
const rerankerModel = ref('')

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
    const topN = Number(rerankerTopN.value || 0)
    results.value = await searchGraph(props.projectId, query.value, {
      searchType: searchType.value,
      useReranker: useReranker.value,
      rerankerModel: rerankerModel.value.trim() || undefined,
      rerankerTopN: useReranker.value ? Math.max(1, Math.min(50, topN || 6)) : undefined,
    })
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
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-500 dark:text-zinc-500" />
        <Input
          v-model="query"
          type="text"
          placeholder="Search knowledge graph..."
          input-class="pl-9 pr-3"
          @keydown.enter="handleSearch"
        />
      </div>
      <Select
        v-model="searchType"
        class="w-44"
      >
        <option v-for="st in searchTypes" :key="st.value" :value="st.value">
          {{ st.label }}
        </option>
      </Select>
      <Button
        :disabled="loading || !query.trim()"
        :loading="loading"
        @click="handleSearch"
      >
        Search
      </Button>
    </div>

    <div class="flex flex-wrap items-center gap-3 rounded-md border border-stone-300/70 bg-stone-100/70 px-3 py-2 dark:border-zinc-700/60 dark:bg-zinc-800/40">
      <label class="inline-flex items-center gap-2 text-xs text-stone-700 dark:text-zinc-300">
        <Checkbox v-model="useReranker" />
        Enable reranker
      </label>
      <Input
        v-model.number="rerankerTopN"
        type="number"
        :min="1"
        :max="50"
        class="w-24"
        placeholder="Top N"
      />
      <Input
        v-model="rerankerModel"
        type="text"
        class="min-w-[180px] flex-1"
        placeholder="Optional reranker model (fallback: project graph_reranker)"
      />
    </div>

    <Alert v-if="error" variant="destructive">
      {{ error }}
    </Alert>

    <div v-if="hasSearched && !loading && results.length === 0 && !error" class="text-center py-6">
      <p class="text-sm text-stone-500 dark:text-zinc-500">No results found</p>
    </div>

    <div v-if="results.length > 0" class="space-y-2 max-h-80 overflow-y-auto">
      <div
        v-for="(result, idx) in results"
        :key="idx"
        class="rounded-lg border border-stone-300/70 bg-stone-100/70 p-3 dark:border-zinc-700/60 dark:bg-zinc-800/40"
      >
        <p class="text-sm text-stone-700 dark:text-zinc-200 whitespace-pre-wrap">
          {{ extractText(result) }}
        </p>
        <div v-if="result.score" class="mt-1">
          <span class="text-xs text-stone-500 dark:text-zinc-500">Score: {{ result.score.toFixed(3) }}</span>
        </div>
        <div v-if="result.reranker_score !== undefined && result.reranker_score !== null" class="mt-1">
          <span class="text-xs text-amber-700 dark:text-amber-300">
            Rerank: {{ Number(result.reranker_score).toFixed(3) }}
            <span v-if="result.reranker_source">({{ result.reranker_source }})</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
