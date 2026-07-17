<script setup lang="ts">
import { ref } from 'vue'
import { Search } from '@lucide/vue'
import { searchProjectMemory } from '@/api/memory'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'

const props = defineProps<{
  projectId: string
}>()

const query = ref('')
const topK = ref(10)
const results = ref<unknown[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const hasSearched = ref(false)

function extractText(result: unknown): string {
  if (typeof result === 'object' && result !== null) {
    const row = result as Record<string, unknown>
    return String(row.content || row.text || JSON.stringify(result, null, 2))
  }
  return String(result)
}

async function handleSearch() {
  if (!query.value.trim()) return
  loading.value = true
  error.value = null
  hasSearched.value = true
  try {
    const payload = await searchProjectMemory(
      props.projectId,
      query.value,
      Math.max(1, Math.min(50, Number(topK.value) || 10)),
    )
    results.value = payload.results
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string; message?: string } }; message?: string }
    error.value = err.response?.data?.detail || err.response?.data?.message || err.message || 'Search failed'
    results.value = []
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-2">
      <div class="relative w-full">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-500 dark:text-zinc-500" />
        <Input
          v-model="query"
          type="text"
          placeholder="Search project memory..."
          input-class="pl-9 pr-3"
          @keydown.enter.prevent="handleSearch"
        />
      </div>
      <div class="flex flex-wrap gap-2">
        <Input v-model.number="topK" type="number" min="1" max="50" class="w-20" />
        <Button :loading="loading" @click="handleSearch">Search</Button>
      </div>
    </div>

    <Alert v-if="error" variant="destructive" class="text-sm">{{ error }}</Alert>

    <div v-if="hasSearched && !loading && results.length === 0 && !error" class="text-xs text-stone-500 dark:text-zinc-500">
      No results.
    </div>

    <ul v-if="results.length" class="space-y-2">
      <li
        v-for="(result, index) in results"
        :key="index"
        class="rounded-md border border-stone-300/80 bg-stone-50/80 p-3 text-xs text-stone-700 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-300"
      >
        <pre class="whitespace-pre-wrap break-words font-sans">{{ extractText(result) }}</pre>
      </li>
    </ul>
  </div>
</template>
