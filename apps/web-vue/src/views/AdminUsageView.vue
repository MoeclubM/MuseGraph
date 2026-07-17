<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import UsageRecordsTable from '@/components/usage/UsageRecordsTable.vue'
import { getAdminUsageRecords } from '@/api/admin'
import type { UsageRecordListResponse } from '@/types'

const { t } = useI18n()

const page = ref(1)
const pageSize = 20
const loading = ref(true)
const error = ref('')
const data = ref<UsageRecordListResponse | null>(null)
const modelFilter = ref('')
const searchFilter = ref('')

function getErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null) {
    const maybe = err as { response?: { data?: { detail?: string } }; message?: string }
    return maybe.response?.data?.detail || maybe.message || fallback
  }
  return fallback
}

async function loadRecords() {
  loading.value = true
  error.value = ''
  try {
    data.value = await getAdminUsageRecords(page.value, pageSize, {
      model: modelFilter.value.trim() || undefined,
      search: searchFilter.value.trim() || undefined,
    })
  } catch (e: unknown) {
    error.value = getErrorMessage(e, t('usageRecords.loadFailed'))
    data.value = null
  } finally {
    loading.value = false
  }
}

async function applyFilters() {
  page.value = 1
  await loadRecords()
}

onMounted(() => {
  void loadRecords()
})
</script>

<template>
  <AdminLayout>
    <div class="muse-page muse-page-shell muse-page-shell-standard space-y-4">
      <header>
        <h1 class="text-xl font-semibold muse-text-heading">{{ t('admin.usageRecords.title') }}</h1>
        <p class="mt-1 text-sm muse-text-muted">
          {{ t('admin.usageRecords.subtitle', { count: data?.total ?? 0 }) }}
        </p>
      </header>
      <UsageRecordsTable
        :data="data"
        :loading="loading"
        :error="error"
        :page="page"
        :page-size="pageSize"
        show-user
        :model-filter="modelFilter"
        @update:model-filter="modelFilter = $event"
        @refresh="loadRecords"
        @apply-filters="applyFilters"
        @prev-page="page--; loadRecords()"
        @next-page="page++; loadRecords()"
      />
    </div>
  </AdminLayout>
</template>