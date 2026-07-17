<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, GitCommit, Loader2, RotateCcw } from '@lucide/vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { getProjectVersions, restoreProjectVersion } from '@/api/projectVersions'
import { useProjectStore } from '@/stores/project'
import type { ProjectRevision } from '@/types'

const route = useRoute()
const router = useRouter()
const projects = useProjectStore()
const projectId = computed(() => String(route.params.id || ''))
const versions = ref<ProjectRevision[]>([])
const loading = ref(false)
const restoring = ref('')

async function load() {
  loading.value = true
  try {
    await projects.fetchProject(projectId.value)
    versions.value = await getProjectVersions(projectId.value)
  } finally {
    loading.value = false
  }
}

async function restore(revision: ProjectRevision) {
  restoring.value = revision.id
  try {
    const run = await restoreProjectVersion(projectId.value, revision.id)
    await router.push(`/projects/${projectId.value}?run=${run.id}`)
  } finally {
    restoring.value = ''
  }
}

watch(projectId, load, { immediate: true })
</script>

<template>
  <AppLayout>
    <div class="mx-auto max-w-3xl space-y-5 py-6">
      <router-link :to="`/projects/${projectId}`" class="inline-flex items-center gap-1 text-sm muse-text-muted">
        <ArrowLeft class="h-4 w-4" />返回工作区
      </router-link>
      <div>
        <h1 class="text-xl font-semibold muse-text-heading">项目版本</h1>
        <p class="mt-1 text-sm muse-text-muted">每个版本同时固定 Git Commit 与不可变 Cognee Dataset。</p>
      </div>
      <div v-if="loading" class="flex justify-center py-16"><Loader2 class="h-5 w-5 animate-spin" /></div>
      <Card v-for="revision in versions" v-else :key="revision.id" class="p-4">
        <div class="flex items-start gap-3">
          <GitCommit class="mt-1 h-4 w-4 muse-text-accent" />
          <div class="min-w-0 flex-1">
            <p class="font-medium muse-text-heading">{{ revision.message }}</p>
            <p class="mt-1 text-xs muse-text-faint">{{ new Date(revision.created_at).toLocaleString() }} · {{ revision.status }}</p>
            <code class="mt-3 block truncate text-xs">{{ revision.git_commit }}</code>
            <code class="mt-1 block truncate text-xs">{{ revision.knowledge_dataset }}</code>
          </div>
          <Button v-if="revision.status !== 'active'" variant="secondary" size="sm" :loading="restoring === revision.id" @click="restore(revision)">
            <RotateCcw class="mr-1 h-3.5 w-3.5" />创建恢复审核
          </Button>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>
