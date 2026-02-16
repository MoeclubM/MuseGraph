import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Project, Operation } from '@/types'
import * as projectsApi from '@/api/projects'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const operations = ref<Operation[]>([])
  const loading = ref(false)
  const projectLoading = ref(false)

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

  async function createProject(data: { title: string; description?: string; content?: string }) {
    const project = await projectsApi.createProject(data)
    projects.value.unshift(project)
    return project
  }

  async function updateProject(
    id: string,
    data: Partial<Pick<Project, 'title' | 'description' | 'content' | 'simulation_requirement' | 'component_models' | 'oasis_analysis'>>
  ) {
    const updated = await projectsApi.updateProject(id, data)
    const idx = projects.value.findIndex((p) => p.id === id)
    if (idx !== -1) projects.value[idx] = updated
    if (currentProject.value?.id === id) currentProject.value = updated
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

  return {
    projects,
    currentProject,
    operations,
    loading,
    projectLoading,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
    fetchOperations,
  }
})
