<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getPublicProjects } from '@/api/projects'
import type { PublicProject } from '@/types'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { Clock, Globe2, Search, UserRound } from '@lucide/vue'

const router = useRouter()
const { t, locale } = useI18n()

const projects = ref<PublicProject[]>([])
const loading = ref(true)
const searchQuery = ref('')
const activeQuery = ref('')

async function loadProjects() {
  loading.value = true
  try {
    const params = activeQuery.value.trim() ? { q: activeQuery.value.trim() } : undefined
    projects.value = await getPublicProjects(params)
  } catch {
    projects.value = []
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  activeQuery.value = searchQuery.value.trim()
  void loadProjects()
}

function clearSearch() {
  searchQuery.value = ''
  activeQuery.value = ''
  void loadProjects()
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

function openProject(project: PublicProject) {
  router.push(`/projects/${project.id}`)
}

onMounted(() => {
  void loadProjects()
})
</script>

<template>
  <AppLayout>
    <div class="muse-page muse-page-shell muse-page-shell-standard">
      <header class="muse-page-hero">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <Globe2 class="h-6 w-6 muse-text-muted" />
            <h1 class="text-2xl muse-text-title">{{ t('plaza.title') }}</h1>
          </div>
          <p class="mt-2 muse-text-caption">{{ t('plaza.subtitle') }}</p>
        </div>
        <form class="flex w-full max-w-md shrink-0 items-center gap-2 sm:w-auto" @submit.prevent="handleSearch">
          <Input
            v-model="searchQuery"
            type="search"
            :placeholder="t('plaza.searchPlaceholder')"
            class="min-w-0 flex-1"
          />
          <Button type="submit" variant="secondary">
            <Search class="h-4 w-4" />
            {{ t('plaza.search') }}
          </Button>
        </form>
      </header>

      <Card v-if="loading" class="flex items-center justify-center py-20">
        <div class="muse-spinner" />
      </Card>

      <Card v-else-if="projects.length === 0" class="py-20 text-center">
        <Globe2 class="mx-auto mb-4 h-12 w-12 muse-text-muted" />
        <h2 class="mb-2 text-lg font-medium muse-text-body">{{ t('plaza.empty.title') }}</h2>
        <p class="text-sm muse-text-muted">
          {{ activeQuery ? t('plaza.empty.searchHint') : t('plaza.empty.hint') }}
        </p>
        <Button v-if="activeQuery" variant="secondary" class="mt-6" @click="clearSearch">
          {{ t('plaza.clearSearch') }}
        </Button>
      </Card>

      <Card v-else>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Card
            v-for="project in projects"
            :key="project.id"
            variant="interactive"
            class="group flex flex-col"
            @click="openProject(project)"
          >
            <div class="flex min-h-0 flex-1 flex-col">
              <h3 class="truncate text-base font-semibold muse-text-body transition-colors group-hover:muse-text-accent">
                {{ project.title }}
              </h3>
              <p v-if="project.description" class="mt-1 line-clamp-3 text-sm muse-text-muted">
                {{ project.description }}
              </p>
              <p v-else class="mt-1 line-clamp-2 text-sm muse-text-faint">
                {{ t('plaza.noDescription') }}
              </p>
              <div class="mt-auto space-y-1.5 pt-3 text-xs muse-text-muted">
                <div class="flex items-center gap-1.5">
                  <UserRound class="h-3.5 w-3.5" />
                  <span>{{ project.author_nickname || t('plaza.anonymousAuthor') }}</span>
                </div>
                <div class="flex items-center gap-1.5">
                  <Clock class="h-3.5 w-3.5" />
                  <span>{{ t('plaza.updatedAt', { date: formatDate(project.updated_at) }) }}</span>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>
