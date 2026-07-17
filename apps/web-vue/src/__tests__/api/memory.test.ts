import { describe, expect, it, vi, beforeEach } from 'vitest'

const getMock = vi.fn()
const postMock = vi.fn()
const deleteMock = vi.fn()

vi.mock('@/api/index', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  },
}))

import {
  getMemoryStatus,
  startMemoryBuildTask,
  deleteProjectMemory,
  getMemoryVisualization,
} from '@/api/memory'

describe('memory api', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    deleteMock.mockReset()
  })

  it('loads memory status', async () => {
    getMock.mockResolvedValue({ data: { status: 'ready', memory_id: 'mem-1' } })
    const status = await getMemoryStatus('project-1')
    expect(getMock).toHaveBeenCalledWith('/api/projects/project-1/memory')
    expect(status.memory_id).toBe('mem-1')
  })

  it('starts memory build task', async () => {
    postMock.mockResolvedValue({ data: { status: 'ok', task: { task_id: 'task-1', status: 'pending' } } })
    const result = await startMemoryBuildTask('project-1', { build_mode: 'rebuild' })
    expect(postMock).toHaveBeenCalledWith('/api/projects/project-1/memory/build/task', {
      text: '',
      build_mode: 'rebuild',
      chapter_ids: undefined,
    })
    expect(result.task.task_id).toBe('task-1')
  })

  it('deletes project memory', async () => {
    deleteMock.mockResolvedValue({})
    await deleteProjectMemory('project-1')
    expect(deleteMock).toHaveBeenCalledWith('/api/projects/project-1/memory')
  })

  it('normalizes visualization payload', async () => {
    getMock.mockResolvedValue({ data: { nodes: [{ id: 'n1' }], edges: null } })
    const graph = await getMemoryVisualization('project-1')
    expect(graph.nodes).toHaveLength(1)
    expect(graph.edges).toEqual([])
  })
})
