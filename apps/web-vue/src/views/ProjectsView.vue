<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useToast } from '@/composables/useToast'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Modal from '@/components/ui/Modal.vue'
import { Plus, FileText, Clock } from 'lucide-vue-next'

const router = useRouter()
const projectStore = useProjectStore()
const toast = useToast()

const showCreateModal = ref(false)
const newTitle = ref('')
const newDescription = ref('')
const creating = ref(false)

onMounted(() => {
  projectStore.fetchProjects()
})

async function handleCreate() {
  if (!newTitle.value.trim()) return
  creating.value = true
  try {
    const project = await projectStore.createProject({
      title: newTitle.value.trim(),
      description: newDescription.value.trim() || undefined,
    })
    showCreateModal.value = false
    newTitle.value = ''
    newDescription.value = ''
    toast.success('Project created successfully')
    router.push(`/projects/${project.id}`)
  } catch {
    // API interceptor handles the error toast
  } finally {
    creating.value = false
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <AppLayout>
    <div class="max-w-5xl mx-auto w-full">
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-bold text-stone-900 dark:text-stone-100">Projects</h1>
          <p class="text-sm text-stone-600 dark:text-stone-400 mt-1">Manage files and chapter-based projects</p>
        </div>
        <Button variant="primary" @click="showCreateModal = true">
          <Plus class="w-4 h-4" />
          New Project
        </Button>
      </div>

      <div v-if="projectStore.loading" class="flex items-center justify-center py-20">
        <div class="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent" />
      </div>

      <div v-else-if="projectStore.projects.length === 0" class="text-center py-20">
        <FileText class="w-12 h-12 mx-auto text-stone-500 dark:text-zinc-500 mb-4" />
        <h2 class="text-lg font-medium text-stone-800 dark:text-stone-200 mb-2">No projects yet</h2>
        <p class="text-sm text-stone-600 dark:text-zinc-400 mb-6">Create your first project to get started with AI-powered writing.</p>
        <Button variant="primary" @click="showCreateModal = true">
          <Plus class="w-4 h-4" />
          Create Project
        </Button>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card
          v-for="project in projectStore.projects"
          :key="project.id"
          class="cursor-pointer hover:border-amber-400/70 transition-colors group"
          @click="router.push(`/projects/${project.id}`)"
        >
          <div class="flex flex-col h-full">
            <h3 class="text-base font-semibold text-stone-900 dark:text-stone-100 group-hover:text-amber-700 dark:group-hover:text-amber-300 transition-colors truncate">
              {{ project.title }}
            </h3>
            <p v-if="project.description" class="text-sm text-stone-700 dark:text-zinc-300 mt-1 line-clamp-2">
              {{ project.description }}
            </p>
            <p
              v-if="project.chapters?.length && (project.chapters[0]?.content || '').trim()"
              class="text-xs text-stone-600 dark:text-zinc-400 mt-2 line-clamp-2"
            >
              {{ (project.chapters[0]?.content || '').substring(0, 120) }}{{ (project.chapters[0]?.content || '').length > 120 ? '...' : '' }}
            </p>
            <div class="flex items-center gap-1.5 mt-auto pt-3 text-xs text-stone-600 dark:text-zinc-400">
              <Clock class="w-3.5 h-3.5" />
              {{ formatDate(project.updated_at) }}
            </div>
          </div>
        </Card>
      </div>
    </div>

    <Modal :show="showCreateModal" title="New Project" @close="showCreateModal = false">
      <form class="space-y-4" @submit.prevent="handleCreate">
        <Input
          v-model="newTitle"
          label="Title"
          placeholder="Project title"
        />
        <div class="space-y-1.5">
          <label class="block text-sm font-medium text-stone-700 dark:text-zinc-300">Description (optional)</label>
          <Textarea
            v-model="newDescription"
            placeholder="Brief description of your project"
            :rows="3"
          />
        </div>
        <div class="flex justify-end gap-3 pt-2">
          <Button variant="ghost" @click="showCreateModal = false">Cancel</Button>
          <Button type="submit" variant="primary" :loading="creating" :disabled="!newTitle.trim()">
            Create
          </Button>
        </div>
      </form>
    </Modal>
  </AppLayout>
</template>
