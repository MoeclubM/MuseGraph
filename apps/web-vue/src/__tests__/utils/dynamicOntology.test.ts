import { describe, expect, it } from 'vitest'
import { collectProjectEntities, groupEntitiesByType } from '@/utils/dynamicOntology'
import type { ProjectFact } from '@/api/facts'

describe('dynamicOntology', () => {
  it('collects entities from facts and structured memory', () => {
    const facts: ProjectFact[] = [
      {
        id: 'f1',
        project_id: 'p1',
        source_kind: 'manual',
        title: '角色',
        content: '林岚是主角',
        content_hash: 'hash',
        memory_status: 'ready',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        entities: [{ id: 'lin', name: '林岚', type: 'Person', summary: '主角' }],
      },
    ]
    const entities = collectProjectEntities({
      facts,
      structuredMemory: {
        places: [{ id: 'port', name: '星港', type: 'Place' }],
      },
    })
    expect(entities.map((item) => item.name).sort()).toEqual(['星港', '林岚'])
  })

  it('groups entities by type', () => {
    const groups = groupEntitiesByType([
      { id: '1', name: 'A', type: 'Person' },
      { id: '2', name: 'B', type: 'Place' },
    ])
    expect(groups.map((group) => group.type)).toEqual(['Person', 'Place'])
  })
})
