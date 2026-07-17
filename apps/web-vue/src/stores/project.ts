import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { Project } from '@/types'
import * as projectsApi from '@/api/projects'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)
  const projectLoading = ref(false)
  let fetchSequence = 0

  function applyProjectUpdate(updated: Project) {
    const index = projects.value.findIndex((project) => project.id === updated.id)
    if (index >= 0) projects.value[index] = updated
    if (currentProject.value?.id === updated.id) currentProject.value = updated
  }

  async function fetchProjects() {
    const sequence = ++fetchSequence
    loading.value = true
    try {
      const result = await projectsApi.getProjects()
      if (sequence === fetchSequence) projects.value = result
      return result
    } finally {
      if (sequence === fetchSequence) loading.value = false
    }
  }

  async function fetchProject(id: string) {
    projectLoading.value = true
    try {
      currentProject.value = await projectsApi.getProject(id)
      return currentProject.value
    } finally {
      projectLoading.value = false
    }
  }

  async function createProject(payload: Parameters<typeof projectsApi.createProject>[0]) {
    const project = await projectsApi.createProject(payload)
    projects.value.unshift(project)
    return project
  }

  async function updateProject(
    id: string,
    payload: Parameters<typeof projectsApi.updateProject>[1],
  ) {
    const project = await projectsApi.updateProject(id, payload)
    applyProjectUpdate(project)
    return project
  }

  async function deleteProject(id: string) {
    await projectsApi.deleteProject(id)
    fetchSequence++
    projects.value = projects.value.filter((project) => project.id !== id)
    if (currentProject.value?.id === id) currentProject.value = null
  }

  return {
    projects,
    currentProject,
    loading,
    projectLoading,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
  }
})
