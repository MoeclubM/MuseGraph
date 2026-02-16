<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { FolderOpen, Plus } from 'lucide-vue-next'

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
  <aside class="w-64 shrink-0 border-r border-slate-700/50 bg-slate-900/50 flex flex-col h-full">
    <div class="flex items-center justify-between p-4 border-b border-slate-700/50">
      <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider">Projects</h2>
      <button
        class="flex items-center justify-center w-7 h-7 rounded-lg text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
        title="New Project"
        @click="emit('create')"
      >
        <Plus class="w-4 h-4" />
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-2">
      <div v-if="projectStore.projects.length === 0" class="px-3 py-8 text-center">
        <FolderOpen class="w-8 h-8 mx-auto text-slate-600 mb-2" />
        <p class="text-sm text-slate-500">No projects yet</p>
      </div>

      <button
        v-for="project in projectStore.projects"
        :key="project.id"
        class="w-full text-left rounded-lg px-3 py-2.5 mb-0.5 transition-colors"
        :class="
          activeId === project.id
            ? 'bg-blue-600/20 text-blue-300 border border-blue-500/30'
            : 'text-slate-300 hover:bg-slate-800 border border-transparent'
        "
        @click="goToProject(project.id)"
      >
        <p class="text-sm font-medium truncate">{{ project.title }}</p>
        <p class="text-xs text-slate-500 mt-0.5">{{ formatDate(project.updated_at) }}</p>
      </button>
    </div>
  </aside>
</template>
