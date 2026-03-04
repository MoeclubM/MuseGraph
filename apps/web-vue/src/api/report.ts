import api from './index'
import type { ReportRuntime } from '@/types'

export async function generateReport(payload: {
  simulation_id: string
  force_regenerate?: boolean
  chapter_ids?: string[]
}): Promise<{ simulation_id: string; report_id: string; task_id?: string; already_generated?: boolean }> {
  const { data } = await api.post<{
    status: string
    data: { simulation_id: string; report_id: string; task_id?: string; already_generated?: boolean }
  }>('/api/report/generate', payload)
  return data.data
}

export async function getReportStatus(payload: {
  task_id?: string
  simulation_id?: string
}): Promise<Record<string, any>> {
  const { data } = await api.post<{ status: string; data: Record<string, any> }>(
    '/api/report/generate/status',
    payload
  )
  return data.data
}

export async function getReport(reportId: string): Promise<ReportRuntime> {
  const { data } = await api.get<{ status: string; data: ReportRuntime }>(`/api/report/${reportId}`)
  return data.data
}

export async function getReportBySimulation(simulationId: string): Promise<ReportRuntime | null> {
  const { data } = await api.get<{ status: string; data: ReportRuntime | null }>(
    `/api/report/by-simulation/${simulationId}`
  )
  return data.data
}

export async function listReports(simulationId?: string): Promise<ReportRuntime[]> {
  const { data } = await api.get<{ status: string; data: ReportRuntime[] }>('/api/report/list', {
    params: simulationId ? { simulation_id: simulationId } : undefined,
  })
  return data.data
}

export async function getReportSections(reportId: string): Promise<Record<string, any>> {
  const { data } = await api.get<{ status: string; data: Record<string, any> }>(
    `/api/report/${reportId}/sections`
  )
  return data.data
}

export async function getSingleReportSection(reportId: string, sectionIndex: number): Promise<Record<string, any>> {
  const { data } = await api.get<{ status: string; data: Record<string, any> }>(
    `/api/report/${reportId}/section/${sectionIndex}`
  )
  return data.data
}

export async function getReportProgress(reportId: string): Promise<Record<string, any>> {
  const { data } = await api.get<{ status: string; data: Record<string, any> }>(
    `/api/report/${reportId}/progress`
  )
  return data.data
}

export async function chatWithReport(payload: {
  simulation_id: string
  message: string
  chat_history?: Array<Record<string, any>>
}): Promise<Record<string, any>> {
  const { data } = await api.post<{ status: string; data: Record<string, any> }>(
    '/api/report/chat',
    payload
  )
  return data.data
}

export async function checkReportStatus(simulationId: string): Promise<Record<string, any>> {
  const { data } = await api.get<{ status: string; data: Record<string, any> }>(
    `/api/report/check/${simulationId}`
  )
  return data.data
}

export async function reportSearch(payload: {
  report_id?: string
  simulation_id?: string
  query: string
}): Promise<Record<string, any>[]> {
  const { data } = await api.post<{ status: string; data: Record<string, any>[] }>(
    '/api/report/tools/search',
    payload
  )
  return data.data
}

export async function reportStatistics(payload: { simulation_id: string }): Promise<Record<string, any>> {
  const { data } = await api.post<{ status: string; data: Record<string, any> }>(
    '/api/report/tools/statistics',
    payload
  )
  return data.data
}
