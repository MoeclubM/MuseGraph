import api from './index'
import type {
  Project,
  Operation,
  ProjectChapter,
  ProjectCharacter,
  ProjectGlossaryTerm,
  ProjectSearchResult,
  ProjectWorldbookEntry,
} from '@/types'

export interface ModelInfo {
  id: string
  provider: string
  name: string
}

export interface RunOperationPayload {
  type: string
  input?: string
  model?: string
  chapter_ids?: string[]
  character_ids?: string[]
  glossary_term_ids?: string[]
  worldbook_entry_ids?: string[]
  include_all_characters?: boolean
  include_all_glossary_terms?: boolean
  include_all_worldbook_entries?: boolean
  use_rag?: boolean
}

export async function getModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/models')
  return data.models
}

export async function getEmbeddingModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/embedding-models')
  return data.models
}

export async function getRerankerModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/reranker-models')
  return data.models
}

export async function getProjects(): Promise<Project[]> {
  const { data } = await api.get<Project[]>('/api/projects')
  return data
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await api.get<Project>(`/api/projects/${id}`)
  return data
}

export async function searchProject(projectId: string, query: string): Promise<ProjectSearchResult[]> {
  const { data } = await api.get<ProjectSearchResult[]>(`/api/projects/${projectId}/search`, {
    params: { q: query },
  })
  return data
}

export async function createProject(payload: {
  title: string
  description?: string
  simulation_requirement?: string
  component_models?: Record<string, string>
  operation_prompts?: Record<string, string>
}): Promise<Project> {
  const { data } = await api.post<Project>('/api/projects', payload)
  return data
}

export async function updateProject(
  id: string,
  payload: Partial<Pick<Project, 'title' | 'description' | 'simulation_requirement' | 'component_models' | 'operation_prompts' | 'oasis_analysis'>>
): Promise<Project> {
  const { data } = await api.put<Project>(`/api/projects/${id}`, payload)
  return data
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/api/projects/${id}`)
}

export async function runOperation(
  projectId: string,
  payload: RunOperationPayload
): Promise<Operation> {
  const { data } = await api.post<Operation>(
    `/api/projects/${projectId}/operation`,
    payload
  )
  return data
}

export async function startOperation(
  projectId: string,
  payload: RunOperationPayload
): Promise<Operation> {
  const { data } = await api.post<Operation>(
    `/api/projects/${projectId}/operation/stream`,
    payload
  )
  return data
}

export async function getOperations(projectId: string): Promise<Operation[]> {
  const { data } = await api.get<Operation[]>(`/api/projects/${projectId}/operations`)
  return data
}

export async function listProjectChapters(projectId: string): Promise<ProjectChapter[]> {
  const { data } = await api.get<ProjectChapter[]>(`/api/projects/${projectId}/chapters`)
  return data
}

export async function createProjectChapter(
  projectId: string,
  payload: {
    title?: string
    content?: string
    order_index?: number
  }
): Promise<ProjectChapter> {
  const { data } = await api.post<ProjectChapter>(`/api/projects/${projectId}/chapters`, payload)
  return data
}

export async function updateProjectChapter(
  projectId: string,
  chapterId: string,
  payload: {
    title?: string
    content?: string
    order_index?: number
  }
): Promise<ProjectChapter> {
  const { data } = await api.put<ProjectChapter>(`/api/projects/${projectId}/chapters/${chapterId}`, payload)
  return data
}

export async function deleteProjectChapter(projectId: string, chapterId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/chapters/${chapterId}`)
}

export async function reorderProjectChapters(
  projectId: string,
  chapterIdsInOrder: string[]
): Promise<ProjectChapter[]> {
  const chapters = chapterIdsInOrder.map((id, index) => ({ id, order_index: index }))
  const { data } = await api.post<ProjectChapter[]>(`/api/projects/${projectId}/chapters/reorder`, { chapters })
  return data
}

export async function listProjectCharacters(projectId: string): Promise<ProjectCharacter[]> {
  const { data } = await api.get<ProjectCharacter[]>(`/api/projects/${projectId}/characters`)
  return data
}

export async function createProjectCharacter(
  projectId: string,
  payload: {
    name: string
    role?: string
    profile?: string
    notes?: string
    order_index?: number
  }
): Promise<ProjectCharacter> {
  const { data } = await api.post<ProjectCharacter>(`/api/projects/${projectId}/characters`, payload)
  return data
}

export async function updateProjectCharacter(
  projectId: string,
  characterId: string,
  payload: {
    name?: string
    role?: string
    profile?: string
    notes?: string
    order_index?: number
  }
): Promise<ProjectCharacter> {
  const { data } = await api.put<ProjectCharacter>(
    `/api/projects/${projectId}/characters/${characterId}`,
    payload
  )
  return data
}

export async function deleteProjectCharacter(projectId: string, characterId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/characters/${characterId}`)
}

export async function listProjectGlossaryTerms(projectId: string): Promise<ProjectGlossaryTerm[]> {
  const { data } = await api.get<ProjectGlossaryTerm[]>(`/api/projects/${projectId}/glossary-terms`)
  return data
}

export async function createProjectGlossaryTerm(
  projectId: string,
  payload: {
    term: string
    definition?: string
    aliases?: string[]
    notes?: string
    order_index?: number
  }
): Promise<ProjectGlossaryTerm> {
  const { data } = await api.post<ProjectGlossaryTerm>(`/api/projects/${projectId}/glossary-terms`, payload)
  return data
}

export async function updateProjectGlossaryTerm(
  projectId: string,
  termId: string,
  payload: {
    term?: string
    definition?: string
    aliases?: string[]
    notes?: string
    order_index?: number
  }
): Promise<ProjectGlossaryTerm> {
  const { data } = await api.put<ProjectGlossaryTerm>(`/api/projects/${projectId}/glossary-terms/${termId}`, payload)
  return data
}

export async function deleteProjectGlossaryTerm(projectId: string, termId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/glossary-terms/${termId}`)
}

export async function listProjectWorldbookEntries(projectId: string): Promise<ProjectWorldbookEntry[]> {
  const { data } = await api.get<ProjectWorldbookEntry[]>(`/api/projects/${projectId}/worldbook-entries`)
  return data
}

export async function createProjectWorldbookEntry(
  projectId: string,
  payload: {
    title: string
    category?: string
    content?: string
    tags?: string[]
    notes?: string
    order_index?: number
  }
): Promise<ProjectWorldbookEntry> {
  const { data } = await api.post<ProjectWorldbookEntry>(`/api/projects/${projectId}/worldbook-entries`, payload)
  return data
}

export async function updateProjectWorldbookEntry(
  projectId: string,
  entryId: string,
  payload: {
    title?: string
    category?: string
    content?: string
    tags?: string[]
    notes?: string
    order_index?: number
  }
): Promise<ProjectWorldbookEntry> {
  const { data } = await api.put<ProjectWorldbookEntry>(`/api/projects/${projectId}/worldbook-entries/${entryId}`, payload)
  return data
}

export async function deleteProjectWorldbookEntry(projectId: string, entryId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/worldbook-entries/${entryId}`)
}
