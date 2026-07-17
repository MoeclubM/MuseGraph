import type { EntityCategory, EntityRecord, ProjectFact } from '@/api/facts'
import type { ProjectOntology } from '@/types'

function normalizeText(value: unknown): string {
  return String(value ?? '').trim()
}

function entityTypeLabel(entityType: string, ontology?: ProjectOntology | null): string {
  const normalized = normalizeText(entityType) || 'Entity'
  const match = ontology?.entity_types?.find(
    (item) => normalizeText(item.name).toLowerCase() === normalized.toLowerCase(),
  )
  return match?.name || normalized
}

function makeEntity(input: {
  id: string
  name: string
  type: string
  summary?: string
  attributes?: Record<string, unknown>
  source?: string
  fact_id?: string | null
  ontology?: ProjectOntology | null
}): EntityRecord | null {
  const id = normalizeText(input.id) || normalizeText(input.name)
  const name = normalizeText(input.name) || id
  if (!id) return null
  return {
    id,
    name,
    type: entityTypeLabel(input.type, input.ontology),
    summary: normalizeText(input.summary),
    source: normalizeText(input.source),
    fact_id: input.fact_id ?? null,
    attributes: input.attributes || {},
  }
}

function appendEntity(bucket: Map<string, EntityRecord>, entity: EntityRecord | null) {
  if (!entity) return
  const existing = bucket.get(entity.id)
  if (!existing) {
    bucket.set(entity.id, entity)
    return
  }
  existing.attributes = { ...(existing.attributes || {}), ...(entity.attributes || {}) }
  if (entity.summary && !existing.summary) existing.summary = entity.summary
  if (entity.source && !String(existing.source || '').includes(entity.source)) {
    existing.source = [existing.source, entity.source].filter(Boolean).join(', ')
  }
}

function entitiesFromStructuredValue(
  key: string,
  value: unknown,
  source: string,
  ontology?: ProjectOntology | null,
): EntityRecord[] {
  const entities: EntityRecord[] = []
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const row = item as Record<string, unknown>
        const entity = makeEntity({
          id: normalizeText(row.id ?? row.name ?? `${key}-${index}`),
          name: normalizeText(row.name ?? row.title ?? row.id ?? `${key}-${index}`),
          type: normalizeText(row.type ?? row.kind ?? key) || key,
          summary: normalizeText(row.summary ?? row.description ?? row.content),
          attributes: Object.fromEntries(
            Object.entries(row).filter(([field]) => !['id', 'name', 'title', 'type', 'kind', 'summary', 'description', 'content'].includes(field)),
          ),
          source,
          ontology,
        })
        if (entity) entities.push(entity)
      } else if (item !== null && item !== undefined && item !== '') {
        const entity = makeEntity({
          id: `${key}-${index}`,
          name: String(item),
          type: key,
          source,
          ontology,
        })
        if (entity) entities.push(entity)
      }
    })
    return entities
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const row = value as Record<string, unknown>
    if ('id' in row || 'name' in row || 'title' in row || 'type' in row) {
      const entity = makeEntity({
        id: normalizeText(row.id ?? row.name ?? key),
        name: normalizeText(row.name ?? row.title ?? row.id ?? key),
        type: normalizeText(row.type ?? row.kind ?? key) || key,
        summary: normalizeText(row.summary ?? row.description),
        attributes: Object.fromEntries(
          Object.entries(row).filter(([field]) => !['id', 'name', 'title', 'type', 'kind', 'summary', 'description'].includes(field)),
        ),
        source,
        ontology,
      })
      if (entity) entities.push(entity)
      return entities
    }
    for (const [nestedKey, nestedValue] of Object.entries(row)) {
      entities.push(...entitiesFromStructuredValue(nestedKey, nestedValue, source, ontology))
    }
  }
  return entities
}

export function collectProjectEntities(input: {
  facts?: ProjectFact[]
  structuredMemory?: Record<string, unknown>
  memorySchema?: Record<string, unknown>
  factGraph?: { nodes?: Record<string, unknown>[] }
  ontology?: ProjectOntology | null
}): EntityRecord[] {
  const bucket = new Map<string, EntityRecord>()
  const facts = input.facts || []

  for (const fact of facts) {
    for (const entity of fact.entities || []) {
      if (!entity || typeof entity !== 'object') continue
      const row = entity as Record<string, unknown>
      appendEntity(
        bucket,
        makeEntity({
          id: normalizeText(row.id ?? row.name),
          name: normalizeText(row.name ?? row.id),
          type: normalizeText(row.type) || 'Entity',
          summary: normalizeText(row.summary),
          attributes: Object.fromEntries(
            Object.entries(row).filter(([field]) => !['id', 'name', 'type', 'summary'].includes(field)),
          ),
          source: `fact:${fact.title || fact.id}`,
          fact_id: fact.id,
          ontology: input.ontology,
        }),
      )
    }
  }

  for (const node of input.factGraph?.nodes || []) {
    appendEntity(
      bucket,
      makeEntity({
        id: normalizeText(node.id ?? node.name),
        name: normalizeText(node.name ?? node.label ?? node.id),
        type: normalizeText(node.type) || 'Entity',
        summary: normalizeText(node.summary ?? node.description),
        attributes: Object.fromEntries(
          Object.entries(node).filter(([field]) => !['id', 'name', 'label', 'type', 'summary', 'description'].includes(field)),
        ),
        source: 'fact_graph',
        ontology: input.ontology,
      }),
    )
  }

  for (const [key, value] of Object.entries(input.structuredMemory || {})) {
    for (const entity of entitiesFromStructuredValue(key, value, 'structured_memory', input.ontology)) {
      appendEntity(bucket, entity)
    }
  }

  for (const [key, value] of Object.entries(input.memorySchema || {})) {
    if (['entity_types', 'edge_types', 'text_type', 'analysis_summary'].includes(key)) continue
    for (const entity of entitiesFromStructuredValue(key, value, 'memory_schema', input.ontology)) {
      appendEntity(bucket, entity)
    }
  }

  return [...bucket.values()].sort((a, b) => {
    const typeCmp = a.type.localeCompare(b.type)
    if (typeCmp !== 0) return typeCmp
    return a.name.localeCompare(b.name)
  })
}

export function groupEntitiesByType(entities: EntityRecord[]): EntityCategory[] {
  const groups = new Map<string, EntityRecord[]>()
  for (const entity of entities) {
    const type = entity.type || 'Entity'
    const list = groups.get(type) || []
    list.push(entity)
    groups.set(type, list)
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([type, items]) => ({
      type,
      label: type,
      count: items.length,
      entities: [...items].sort((a, b) => a.name.localeCompare(b.name)),
    }))
}

export function formatEntityAttributeValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}
