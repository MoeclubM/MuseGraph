import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const ADMIN_EMAIL = process.env.PW_ADMIN_EMAIL || 'admin@example.com'
const ADMIN_PASSWORD = process.env.PW_ADMIN_PASSWORD || 'Admin123!Pass'
const PROVIDER_NAME = process.env.PW_PROVIDER_NAME || 'PW OpenAI-Compatible'
const PROVIDER_BASE_URL = process.env.PW_PROVIDER_BASE_URL || ''
const REQUESTED_MODEL_NAME = process.env.PW_MODEL_NAME || ''
const REQUESTED_EMBEDDING_MODEL_NAME = process.env.PW_EMBEDDING_MODEL_NAME || ''
const PROVIDER_API_KEY = process.env.PW_PROVIDER_API_KEY || ''
const TEST_USER_PASSWORD = process.env.PW_TEST_USER_PASSWORD || 'User123!Pass'
const AGENT_TIMEOUT_MS = Number(process.env.PW_AGENT_TIMEOUT_MS || 20 * 60 * 1000)
const AGENT_POLL_MS = Number(process.env.PW_AGENT_POLL_MS || 5000)

const SAMPLE_CHAPTER = `Harbor Transit Compact Fixture

Lena Torres coordinates ferry operations for TideLine Ferries in Greywake Bay. After a morning traffic failure blocks East Pier, the city transport office, TideLine Ferries, the hospital, port vendors, and neighborhood representatives form a temporary coordination room.

The pilot plan has three linked events. TideLine adds two early ferry departures, the city reserves a bus lane between East Pier and the hospital annex, and community monitors report delays every two hours. Port vendors fear delivery delays, commuters demand faster service, and operators warn that crews cannot work unlimited overtime.

During the review meeting, Lena explains that missed ferry connections cause hospital shift gaps. Malik Chen from the neighborhood council asks for transparent checkpoints. The group agrees to track ferry wait time, bus reliability, emergency vehicle clearance, and public complaint volume. If any threshold fails twice, the coordination room revises schedules before the next morning.`

function e2eLog(message: string) {
  console.log(`[E2E] ${message}`)
}

interface AdminProvider {
  id: string
  name: string
  provider: string
  base_url?: string
  models: string[]
  embedding_models: string[]
  is_active: boolean
  priority: number
}

interface AdminUser {
  id: string
  email: string
}

interface ModelSelection {
  model: string
  embeddingModel: string
}

test.describe('Docker Full Flow', () => {
  test('register user, configure provider/pricing and run agent workspace flow', async ({ page, request }) => {
    test.setTimeout(35 * 60 * 1000)

    const testUserEmail = `pw-user-${Date.now()}@example.com`

    await registerTestUserInApi(request, testUserEmail)

    const adminToken = await loginAdminInApi(request)
    const provider = await upsertProviderInAdminApi(request, adminToken)
    const modelSelection = await ensureProviderModelsInAdminApi(request, adminToken, provider)
    await upsertPricingInAdminApi(request, adminToken, modelSelection.model)
    await tuneLlmRuntimeInAdminApi(request, adminToken)
    await topUpUserBalanceInAdminApi(request, adminToken, testUserEmail, 500)
    await login(page, testUserEmail, TEST_USER_PASSWORD)
    const userToken = await getAuthToken(page)

    const projectId = await createProjectFromDashboard(page)
    await configureProjectAgentModels(request, userToken, projectId, modelSelection)
    await seedChapterFixture(request, userToken, projectId)
    await runAgentChatTurn(page, request, userToken, projectId, modelSelection.model)
  })
})

async function loginAdminInApi(request: APIRequestContext): Promise<string> {
  e2eLog('Admin auth: requesting admin token via API')
  const response = await request.fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    data: {
      email: ADMIN_EMAIL,
      password: ADMIN_PASSWORD,
    },
  })
  if (!response.ok()) {
    const detail = (await response.text()).slice(0, 800)
    throw new Error(`POST /api/auth/login failed: ${response.status()} ${detail}`)
  }
  const payload = (await response.json()) as { token?: string; user?: { is_admin?: boolean } }
  if (!payload.token) {
    throw new Error('Admin auth response did not include a token')
  }
  if (!payload.user?.is_admin) {
    throw new Error('Admin auth response did not return an admin user')
  }
  return payload.token
}

async function login(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('输入密码').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

async function registerTestUserInApi(request: APIRequestContext, email: string) {
  e2eLog(`Auth bootstrap: registering ${email} via API`)
  const response = await request.fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    data: {
      email,
      password: TEST_USER_PASSWORD,
      nickname: 'PW Test User',
    },
  })
  if (!response.ok()) {
    const detail = (await response.text()).slice(0, 800)
    throw new Error(`POST /api/auth/register failed: ${response.status()} ${detail}`)
  }
}

async function getAuthToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => localStorage.getItem('token') || '')
  if (!token) {
    throw new Error('Expected auth token in localStorage, but token is empty')
  }
  return token
}

async function adminApi<T>(
  request: APIRequestContext,
  token: string,
  method: 'GET' | 'POST' | 'PUT',
  url: string,
  data?: Record<string, unknown>
): Promise<T> {
  const response = await request.fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data,
  })
  if (!response.ok()) {
    const detail = (await response.text()).slice(0, 800)
    throw new Error(`${method} ${url} failed: ${response.status()} ${detail}`)
  }
  if (response.status() === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

async function upsertProviderInAdminApi(request: APIRequestContext, token: string): Promise<AdminProvider> {
  const providers = await adminApi<AdminProvider[]>(request, token, 'GET', '/api/admin/providers')
  const existing = providers.find((item) => item.name === PROVIDER_NAME)

  if (existing) {
    const payload: Record<string, unknown> = {
      name: PROVIDER_NAME,
      provider: 'openai_compatible',
      is_active: true,
      priority: 100,
    }
    if (PROVIDER_BASE_URL) payload.base_url = PROVIDER_BASE_URL
    if (PROVIDER_API_KEY) payload.api_key = PROVIDER_API_KEY
    return await adminApi<AdminProvider>(
      request,
      token,
      'PUT',
      `/api/admin/providers/${existing.id}`,
      payload
    )
  }

  if (!PROVIDER_API_KEY) {
    const fallback = providers.find((item) => item.is_active) || providers[0]
    if (!fallback) {
      throw new Error(
        'No available provider. Configure one in WebUI first or set PW_PROVIDER_API_KEY for automated setup.'
      )
    }
    return fallback
  }

  const payload: Record<string, unknown> = {
    name: PROVIDER_NAME,
    provider: 'openai_compatible',
    api_key: PROVIDER_API_KEY,
    is_active: true,
    priority: 100,
  }
  if (PROVIDER_BASE_URL) payload.base_url = PROVIDER_BASE_URL
  return await adminApi<AdminProvider>(request, token, 'POST', '/api/admin/providers', payload)
}

async function ensureProviderModelsInAdminApi(
  request: APIRequestContext,
  token: string,
  provider: AdminProvider
): Promise<ModelSelection> {
  const providers = await adminApi<AdminProvider[]>(request, token, 'GET', '/api/admin/providers')
  const latest = providers.find((item) => item.id === provider.id)
  if (!latest) {
    throw new Error(`Provider ${provider.name} not found after setup`)
  }

  let model = REQUESTED_MODEL_NAME || latest.models?.[0] || ''
  if (!model) {
    throw new Error(
      'No chat model available. Add chat model in WebUI or set PW_MODEL_NAME for this e2e run.'
    )
  }

  if (!latest.models.includes(model)) {
    await adminApi(request, token, 'POST', `/api/admin/providers/${latest.id}/models`, { model })
  }

  let embeddingModel = REQUESTED_EMBEDDING_MODEL_NAME || latest.embedding_models?.[0] || ''
  if (!embeddingModel) {
    embeddingModel = providers.find((item) => item.embedding_models?.[0])?.embedding_models?.[0] || ''
  }
  if (!embeddingModel) {
    throw new Error(
      'No embedding model available. Add embedding model in WebUI or set PW_EMBEDDING_MODEL_NAME for this e2e run.'
    )
  }

  const embeddingProvider = providers.find((item) => item.embedding_models.includes(embeddingModel))
  if (!embeddingProvider) {
    await adminApi(request, token, 'POST', `/api/admin/providers/${latest.id}/embedding-models`, {
      model: embeddingModel,
    })
  }

  model = model.trim()
  embeddingModel = embeddingModel.trim()
  return { model, embeddingModel }
}

async function upsertPricingInAdminApi(request: APIRequestContext, token: string, modelName: string) {
  const pricingRules = await adminApi<Array<{ id: string; model: string }>>(request, token, 'GET', '/api/admin/pricing')
  const existing = pricingRules.find((rule) => rule.model === modelName)
  if (existing) {
    await adminApi(request, token, 'PUT', `/api/admin/pricing/${existing.id}`, {
      model: modelName,
      billing_mode: 'TOKEN',
      input_price: 1.1,
      output_price: 4.4,
      token_unit: 1000000,
      is_active: true,
    })
    return
  }

  await adminApi(request, token, 'POST', '/api/admin/pricing', {
    model: modelName,
    billing_mode: 'TOKEN',
    input_price: 1.1,
    output_price: 4.4,
    token_unit: 1000000,
    is_active: true,
  })
}

async function tuneLlmRuntimeInAdminApi(request: APIRequestContext, token: string) {
  const current = await adminApi<Record<string, unknown>>(request, token, 'GET', '/api/admin/llm-runtime-config')
  await adminApi(request, token, 'PUT', '/api/admin/llm-runtime-config', {
    ...current,
    llm_request_timeout_seconds: 600,
    llm_retry_count: 1,
    llm_retry_interval_seconds: 1,
    llm_prefer_stream: false,
    llm_stream_fallback_nonstream: true,
    llm_openai_api_style: 'chat_completions',
    llm_reasoning_effort: 'low',
  })
}

async function topUpUserBalanceInAdminApi(
  request: APIRequestContext,
  token: string,
  email: string,
  amount: number
) {
  const usersPayload = await adminApi<{ users: AdminUser[] }>(
    request,
    token,
    'GET',
    `/api/admin/users?search=${encodeURIComponent(email)}&page=1&page_size=20`
  )
  const target = usersPayload.users.find((user) => user.email === email)
  if (!target) {
    throw new Error(`Cannot find user ${email} in admin list`)
  }

  await adminApi(request, token, 'POST', `/api/admin/users/${target.id}/balance`, {
    amount,
  })
}

async function createProjectFromDashboard(page: Page): Promise<string> {
  e2eLog('Create project: open projects page')
  await page.goto('/projects')
  await expect(page.getByRole('heading', { name: '项目', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /New Project|Create Project/i }).first().click()
  await page.getByPlaceholder('Project title').fill(`E2E Full Flow ${Date.now()}`)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+$/)
  e2eLog('Create project: waiting for agent workspace')
  await expect(page.getByTestId('agent-chat-input')).toBeVisible({ timeout: 60000 })
  return currentProjectId(page)
}

async function configureProjectAgentModels(
  request: APIRequestContext,
  token: string,
  projectId: string,
  selection: ModelSelection,
) {
  const getRes = await request.fetch(`/api/projects/${projectId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!getRes.ok()) {
    throw new Error(`GET /api/projects/${projectId} failed: ${getRes.status()}`)
  }
  const project = (await getRes.json()) as { component_models?: Record<string, string> }
  const componentModels = {
    ...(project.component_models || {}),
    operation_agent_task: selection.model,
    memory_build: selection.model,
    memory_embedding: selection.embeddingModel,
    memory_reranker: process.env.PW_RERANKER_MODEL || selection.embeddingModel,
  }
  const putRes = await request.fetch(`/api/projects/${projectId}`, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: { component_models: componentModels },
  })
  if (!putRes.ok()) {
    throw new Error(`PUT /api/projects/${projectId} failed: ${putRes.status()}`)
  }
}

async function seedChapterFixture(request: APIRequestContext, token: string, projectId: string) {
  e2eLog('Agent flow: seed chapter fixture via API')
  const response = await request.fetch(`/api/projects/${projectId}/chapters`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: { title: 'E2E Harbor Fixture', content: SAMPLE_CHAPTER },
  })
  if (!response.ok()) {
    const detail = (await response.text()).slice(0, 800)
    throw new Error(`POST chapter failed: ${response.status()} ${detail}`)
  }
}

async function runAgentChatTurn(
  page: Page,
  request: APIRequestContext,
  token: string,
  projectId: string,
  model: string,
) {
  e2eLog('Agent flow: send chat from workspace UI')
  const textarea = page.getByTestId('agent-chat-input')
  await textarea.fill(
    '请简要分析这段港口交通协调素材中的主要角色与冲突，并给出 3 条可执行的后续写作建议。'
  )
  const select = page.locator('select').first()
  if (await select.count()) {
    await select.selectOption(model)
  }
  const chatResponse = page.waitForResponse(
    (res) =>
      res.url().includes(`/api/projects/${projectId}/agent/chat`)
      && res.request().method() === 'POST'
      && res.status() === 202,
    { timeout: 60000 },
  )
  await page.getByTestId('agent-send-button').click()
  const response = await chatResponse
  const payload = (await response.json()) as { session_id: string }
  await waitForAgentSession(request, token, projectId, payload.session_id)
  e2eLog('Agent flow: session completed')
}

async function waitForAgentSession(
  request: APIRequestContext,
  token: string,
  projectId: string,
  sessionId: string,
  timeoutMs = AGENT_TIMEOUT_MS,
) {
  const deadline = Date.now() + timeoutMs
  let lastStatus = 'unknown'
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, AGENT_POLL_MS))
    const response = await request.fetch(`/api/projects/${projectId}/agent/chat/${sessionId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok()) {
      lastStatus = `error:${response.status()}`
      continue
    }
    const session = (await response.json()) as { status?: string }
    lastStatus = String(session.status || '')
    if (['completed', 'failed', 'partial'].includes(lastStatus)) {
      if (lastStatus === 'failed') {
        throw new Error(`Agent session failed: ${sessionId}`)
      }
      return
    }
  }
  throw new Error(`Agent session timed out (last status: ${lastStatus})`)
}

async function currentProjectId(page: Page): Promise<string> {
  const match = page.url().match(/\/projects\/([^/?#]+)/)
  if (!match || !match[1]) {
    throw new Error(`Cannot resolve project id from URL: ${page.url()}`)
  }
  return match[1]
}
