<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { FolderOpen, Plus } from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'

const router = useRouter()
const projectStore = useProjectStore()

onMounted(() => {
  if (projectStore.projects.length === 0) {
    projectStore.fetchProjects()
  }
})

defineProps<{
  activeId?: string
}>()

const emit = defineEmits<{
  create: []
}>()

function goToProject(id: string) {
  router.push(`/projects/${id}`)
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}
</script>

<template>
  <aside class="flex h-full w-64 shrink-0 flex-col rounded-l-md border-r border-stone-300/80 bg-[#efe8da]/90 dark:border-zinc-700/40 dark:bg-zinc-900/60">
    <div class="flex items-center justify-between p-4 border-b border-stone-300/80 dark:border-zinc-700/40">
      <h2 class="text-sm font-semibold text-stone-700 dark:text-stone-300 uppercase tracking-wider">Projects</h2>
      <Button
        variant="ghost"
        size="sm"
        class="h-7 w-7 p-0 text-stone-500 dark:text-stone-400"
        title="New Project"
        @click="emit('create')"
      >
        <Plus class="w-4 h-4" />
      </Button>
    </div>

    <div class="flex-1 overflow-y-auto p-2">
      <div v-if="projectStore.projects.length === 0" class="px-3 py-8 text-center">
        <FolderOpen class="w-8 h-8 mx-auto text-stone-500 dark:text-zinc-500 mb-2" />
        <p class="text-sm text-stone-500 dark:text-zinc-500">No projects yet</p>
      </div>

      <Button
        v-for="project in projectStore.projects"
        :key="project.id"
        variant="ghost"
        size="sm"
        class="mb-0.5 h-auto w-full justify-start px-3 py-2.5 text-left"
        :class="
          activeId === project.id
            ? 'border border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300'
            : 'border border-transparent text-stone-700 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-zinc-800'
        "
        @click="goToProject(project.id)"
      >
        <p class="text-sm font-medium truncate">{{ project.title }}</p>
        <p class="text-xs text-stone-500 mt-0.5">{{ formatDate(project.updated_at) }}</p>
      </Button>
    </div>
  </aside>
</template>
