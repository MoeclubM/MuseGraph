import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { Project, ProjectChapter } from '@/types'
import * as projectsApi from '@/api/projects'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)
  const projectLoading = ref(false)
  const chapterSaving = ref(false)
  let fetchProjectsSeq = 0

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
    const seq = ++fetchProjectsSeq
    loading.value = true
    try {
      const data = await projectsApi.getProjects()
      if (seq !== fetchProjectsSeq) return data
      projects.value = data
      return data
    } finally {
      if (seq === fetchProjectsSeq) loading.value = false
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
    data: Partial<Pick<Project, 'title' | 'description' | 'component_models' | 'operation_prompts'>>
  ) {
    const updated = await projectsApi.updateProject(id, data)
    applyProjectUpdate(updated)
    return updated
  }

  async function deleteProject(id: string) {
    await projectsApi.deleteProject(id)
    fetchProjectsSeq += 1
    projects.value = projects.value.filter((p) => p.id !== id)
    if (currentProject.value?.id === id) currentProject.value = null
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
    loading,
    projectLoading,
    chapterSaving,
    orderedChapters,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
    fetchChapters,
    createChapter,
    updateChapter,
    deleteChapter,
    reorderChapters,
  }
})
