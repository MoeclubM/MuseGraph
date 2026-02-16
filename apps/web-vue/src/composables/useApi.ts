import { ref } from 'vue'

export function useApi<T>(fn: (...args: any[]) => Promise<T>) {
  const data = ref<T | null>(null) as { value: T | null }
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function execute(...args: any[]): Promise<T | null> {
    loading.value = true
    error.value = null
    try {
      const result = await fn(...args)
      data.value = result
      return result
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.response?.data?.message || e.message || 'An error occurred'
      return null
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, execute }
}
