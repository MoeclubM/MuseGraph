import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useProjectStore } from '@/stores/project'

vi.mock('@/api/projects', () => ({
  getProjects: vi.fn(),
  getProject: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  getOperations: vi.fn(),
}))

import * as projectsApi from '@/api/projects'

const mockProject = {
  id: 'proj-1',
  user_id: 'user-1',
  title: 'Test Project',
  description: 'A test project',
  content: 'Some content',
  cognee_dataset_id: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

const mockProject2 = {
  id: 'proj-2',
  user_id: 'user-1',
  title: 'Second Project',
  description: null,
  content: '',
  cognee_dataset_id: null,
  created_at: '2024-01-02T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
}

describe('Project Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should have empty projects array', () => {
      const store = useProjectStore()
      expect(store.projects).toEqual([])
    })

    it('should have null currentProject', () => {
      const store = useProjectStore()
      expect(store.currentProject).toBeNull()
    })

    it('should have empty operations array', () => {
      const store = useProjectStore()
      expect(store.operations).toEqual([])
    })

    it('should have loading set to false', () => {
      const store = useProjectStore()
      expect(store.loading).toBe(false)
    })
  })

  describe('fetchProjects', () => {
    it('should populate projects from API', async () => {
      vi.mocked(projectsApi.getProjects).mockResolvedValue([mockProject, mockProject2])

      const store = useProjectStore()
      await store.fetchProjects()

      expect(projectsApi.getProjects).toHaveBeenCalled()
      expect(store.projects).toEqual([mockProject, mockProject2])
    })

    it('should set loading to true during fetch and false after', async () => {
      let resolvePromise: (value: any) => void
      vi.mocked(projectsApi.getProjects).mockImplementation(
        () => new Promise((resolve) => { resolvePromise = resolve })
      )

      const store = useProjectStore()
      const promise = store.fetchProjects()

      expect(store.loading).toBe(true)

      resolvePromise!([mockProject])
      await promise

      expect(store.loading).toBe(false)
    })

    it('should set loading to false even on error', async () => {
      vi.mocked(projectsApi.getProjects).mockRejectedValue(new Error('Network error'))

      const store = useProjectStore()
      await expect(store.fetchProjects()).rejects.toThrow('Network error')

      expect(store.loading).toBe(false)
    })
  })

  describe('createProject', () => {
    it('should call API and prepend project to list', async () => {
      vi.mocked(projectsApi.createProject).mockResolvedValue(mockProject)

      const store = useProjectStore()
      const result = await store.createProject({ title: 'Test Project', description: 'A test project' })

      expect(projectsApi.createProject).toHaveBeenCalledWith({
        title: 'Test Project',
        description: 'A test project',
      })
      expect(result).toEqual(mockProject)
      expect(store.projects[0]).toEqual(mockProject)
    })

    it('should prepend new project to existing list', async () => {
      vi.mocked(projectsApi.getProjects).mockResolvedValue([mockProject2])
      vi.mocked(projectsApi.createProject).mockResolvedValue(mockProject)

      const store = useProjectStore()
      await store.fetchProjects()
      await store.createProject({ title: 'Test Project' })

      expect(store.projects).toHaveLength(2)
      expect(store.projects[0]).toEqual(mockProject)
      expect(store.projects[1]).toEqual(mockProject2)
    })

    it('should propagate error on failure', async () => {
      vi.mocked(projectsApi.createProject).mockRejectedValue(new Error('Quota exceeded'))

      const store = useProjectStore()
      await expect(store.createProject({ title: 'Fail' })).rejects.toThrow('Quota exceeded')
    })
  })

  describe('deleteProject', () => {
    it('should remove project from list', async () => {
      vi.mocked(projectsApi.getProjects).mockResolvedValue([mockProject, mockProject2])
      vi.mocked(projectsApi.deleteProject).mockResolvedValue(undefined)

      const store = useProjectStore()
      await store.fetchProjects()
      await store.deleteProject('proj-1')

      expect(projectsApi.deleteProject).toHaveBeenCalledWith('proj-1')
      expect(store.projects).toHaveLength(1)
      expect(store.projects[0].id).toBe('proj-2')
    })

    it('should clear currentProject if it matches deleted id', async () => {
      vi.mocked(projectsApi.getProject).mockResolvedValue(mockProject)
      vi.mocked(projectsApi.deleteProject).mockResolvedValue(undefined)

      const store = useProjectStore()
      await store.fetchProject('proj-1')
      expect(store.currentProject).toEqual(mockProject)

      await store.deleteProject('proj-1')
      expect(store.currentProject).toBeNull()
    })

    it('should not clear currentProject if different id is deleted', async () => {
      vi.mocked(projectsApi.getProjects).mockResolvedValue([mockProject, mockProject2])
      vi.mocked(projectsApi.getProject).mockResolvedValue(mockProject)
      vi.mocked(projectsApi.deleteProject).mockResolvedValue(undefined)

      const store = useProjectStore()
      await store.fetchProjects()
      await store.fetchProject('proj-1')
      await store.deleteProject('proj-2')

      expect(store.currentProject).toEqual(mockProject)
    })

    it('should propagate error on failure', async () => {
      vi.mocked(projectsApi.deleteProject).mockRejectedValue(new Error('Not found'))

      const store = useProjectStore()
      await expect(store.deleteProject('nonexistent')).rejects.toThrow('Not found')
    })
  })
})
