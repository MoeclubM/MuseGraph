import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { Project, Operation, ProjectChapter } from '@/types'
import * as projectsApi from '@/api/projects'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const operations = ref<Operation[]>([])
  const loading = ref(false)
  const projectLoading = ref(false)
  const chapterSaving = ref(false)

  const orderedChapters = computed<ProjectChapter[]>(() => {
    const chapters = currentProject.value?.chapters || []
    return [...chapters].sort((a, b) => a.order_index - b.order_index)
  })

  function applyProjectUpdate(updated: Project) {
    const idx = projects.value.findIndex((p) => p.id === updated.id)
    if (idx !== -1) projects.value[idx] = updated
    if (currentProject.value?.id === updated.id) currentProject.value = updated
  }

  async function fetchProjects() {
    loading.value = true
    try {
      projects.value = await projectsApi.getProjects()
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id: string) {
    projectLoading.value = true
    try {
      currentProject.value = await projectsApi.getProject(id)
    } finally {
      projectLoading.value = false
    }
  }

  async function createProject(
    data: {
      title: string
      description?: string
      simulation_requirement?: string
      component_models?: Record<string, string>
      operation_prompts?: Record<string, string>
    }
  ) {
    const project = await projectsApi.createProject(data)
    projects.value.unshift(project)
    return project
  }

  async function updateProject(
    id: string,
    data: Partial<Pick<Project, 'title' | 'description' | 'simulation_requirement' | 'component_models' | 'operation_prompts' | 'oasis_analysis'>>
  ) {
    const updated = await projectsApi.updateProject(id, data)
    applyProjectUpdate(updated)
    return updated
  }

  async function deleteProject(id: string) {
    await projectsApi.deleteProject(id)
    projects.value = projects.value.filter((p) => p.id !== id)
    if (currentProject.value?.id === id) currentProject.value = null
  }

  async function fetchOperations(projectId: string) {
    try {
      operations.value = await projectsApi.getOperations(projectId)
    } catch {
      operations.value = []
    }
  }

  async function fetchChapters(projectId: string) {
    chapterSaving.value = true
    try {
      const chapters = await projectsApi.listProjectChapters(projectId)
      if (currentProject.value?.id === projectId) {
        currentProject.value = {
          ...currentProject.value,
          chapters,
        }
      }
      return chapters
    } finally {
      chapterSaving.value = false
    }
  }

  async function createChapter(
    projectId: string,
    payload: {
      title?: string
      content?: string
      order_index?: number
    } = {}
  ) {
    chapterSaving.value = true
    try {
      await projectsApi.createProjectChapter(projectId, payload)
      await fetchProject(projectId)
      await fetchChapters(projectId)
      return orderedChapters.value
    } finally {
      chapterSaving.value = false
    }
  }

  async function updateChapter(
    projectId: string,
    chapterId: string,
    payload: {
      title?: string
      content?: string
      order_index?: number
    }
  ) {
    chapterSaving.value = true
    try {
      await projectsApi.updateProjectChapter(projectId, chapterId, payload)
      await fetchProject(projectId)
      await fetchChapters(projectId)
      return orderedChapters.value
    } finally {
      chapterSaving.value = false
    }
  }

  async function deleteChapter(projectId: string, chapterId: string) {
    chapterSaving.value = true
    try {
      await projectsApi.deleteProjectChapter(projectId, chapterId)
      await fetchProject(projectId)
      await fetchChapters(projectId)
      return orderedChapters.value
    } finally {
      chapterSaving.value = false
    }
  }

  async function reorderChapters(projectId: string, chapterIdsInOrder: string[]) {
    chapterSaving.value = true
    try {
      await projectsApi.reorderProjectChapters(projectId, chapterIdsInOrder)
      await fetchProject(projectId)
      return orderedChapters.value
    } finally {
      chapterSaving.value = false
    }
  }

  return {
    projects,
    currentProject,
    operations,
    loading,
    projectLoading,
    chapterSaving,
    orderedChapters,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
    fetchOperations,
    fetchChapters,
    createChapter,
    updateChapter,
    deleteChapter,
    reorderChapters,
  }
})
