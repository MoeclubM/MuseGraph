import { describe, expect, it, vi, beforeEach } from 'vitest'
import api from '@/api/index'
import { deleteProject, getPublicProjects, updateProjectVisibility } from '@/api/projects'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('projects api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches public projects with optional search', async () => {
    const payload = [
      {
        id: 'proj-public',
        title: 'Open Novel',
        description: 'Shared work',
        visibility: 'public',
        author_nickname: 'Ada',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
      },
    ]
    vi.mocked(api.get).mockResolvedValue({ data: payload })

    const result = await getPublicProjects({ q: 'novel' })

    expect(api.get).toHaveBeenCalledWith('/api/projects/public', { params: { q: 'novel' } })
    expect(result).toEqual(payload)
  })

  it('updates project visibility', async () => {
    const payload = {
      id: 'proj-1',
      user_id: 'user-1',
      title: 'My Project',
      description: null,
      visibility: 'public',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
    }
    vi.mocked(api.put).mockResolvedValue({ data: payload })

    const result = await updateProjectVisibility('proj-1', 'public')

    expect(api.put).toHaveBeenCalledWith('/api/projects/proj-1/visibility', { visibility: 'public' })
    expect(result.visibility).toBe('public')
  })

  it('deletes a project by id', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: undefined })

    await deleteProject('proj-1')

    expect(api.delete).toHaveBeenCalledWith('/api/projects/proj-1')
  })
})
