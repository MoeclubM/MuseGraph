<script setup lang="ts">
import { ref, onActivated, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useProjectStore } from '@/stores/project'
import { useToast } from '@/composables/useToast'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import { Plus, FileText, Clock } from '@lucide/vue'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const projectStore = useProjectStore()
const toast = useToast()

const showCreateModal = ref(false)
const newTitle = ref('')
const newDescription = ref('')
const creating = ref(false)

function refreshProjects() {
  void projectStore.fetchProjects()
}

onMounted(refreshProjects)
onActivated(refreshProjects)

watch(
  () => route.name,
  (name) => {
    if (name === 'projects') refreshProjects()
  }
)

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
    toast.success(t('toast.projectCreated'))
    router.push(`/projects/${project.id}`)
  } catch {
    // API interceptor handles the error toast
  } finally {
    creating.value = false
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString(locale.value === 'zh-CN' ? 'zh-CN' : 'en-US', {
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
    <div class="muse-page muse-page-shell muse-page-shell-standard">
      <header class="muse-page-hero">
        <div class="min-w-0 flex-1">
          <h1 class="text-2xl muse-text-title">{{ t('projects.title') }}</h1>
          <p class="mt-2 muse-text-caption">{{ t('projects.subtitle') }}</p>
        </div>
        <Button variant="primary" class="shrink-0" @click="showCreateModal = true">
          <Plus class="w-4 h-4" />
          {{ t('projects.newProject') }}
        </Button>
      </header>

      <Card v-if="projectStore.loading" class="flex items-center justify-center py-20">
        <div class="muse-spinner" />
      </Card>

      <Card v-else-if="projectStore.projects.length === 0" class="py-20 text-center">
        <FileText class="w-12 h-12 mx-auto text-stone-500 dark:text-zinc-500 mb-4" />
        <h2 class="text-lg font-medium muse-text-body mb-2">{{ t('projects.empty.title') }}</h2>
        <p class="text-sm muse-text-muted mb-6">{{ t('projects.empty.hint') }}</p>
        <Button variant="primary" @click="showCreateModal = true">
          <Plus class="w-4 h-4" />
          {{ t('projects.createProject') }}
        </Button>
      </Card>

      <Card v-else>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Card
            v-for="project in projectStore.projects"
            :key="project.id"
            variant="interactive"
            class="group flex flex-col"
            @click="router.push(`/projects/${project.id}`)"
          >
            <div class="flex min-h-0 flex-1 flex-col">
              <h3 class="truncate text-base font-semibold muse-text-body transition-colors group-hover:muse-text-accent">
                {{ project.title }}
              </h3>
              <p v-if="project.description" class="text-sm muse-text-muted mt-1 line-clamp-2">
                {{ project.description }}
              </p>
              <p class="mt-2 text-xs muse-text-faint">{{ project.pack_slug }} · {{ project.visibility }}</p>
              <div class="flex items-center gap-1.5 mt-auto pt-3 text-xs muse-text-muted">
                <Clock class="w-3.5 h-3.5" />
                {{ formatDate(project.updated_at) }}
              </div>
            </div>
          </Card>
        </div>
      </Card>
    </div>

    <Modal :show="showCreateModal" :title="t('projects.modal.title')" @close="showCreateModal = false">
      <form class="space-y-4" @submit.prevent="handleCreate">
        <Input
          v-model="newTitle"
          :label="t('projects.modal.titleLabel')"
          :placeholder="t('projects.modal.titlePlaceholder')"
        />
        <Input
          v-model="newDescription"
          :label="t('projects.modal.descriptionLabel')"
          :placeholder="t('projects.modal.descriptionPlaceholder')"
        />
        <div class="flex justify-end gap-3 pt-2">
          <Button variant="ghost" @click="showCreateModal = false">{{ t('common.cancel') }}</Button>
          <Button type="submit" variant="primary" :loading="creating" :disabled="!newTitle.trim()">
            {{ t('common.create') }}
          </Button>
        </div>
      </form>
    </Modal>
  </AppLayout>
</template>
