import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test'

const ADMIN_EMAIL = process.env.PW_ADMIN_EMAIL || 'admin@example.com'
const ADMIN_PASSWORD = process.env.PW_ADMIN_PASSWORD || 'Admin123!Pass'
const PROVIDER_NAME = process.env.PW_PROVIDER_NAME || 'PW OpenAI-Compatible'
const PROVIDER_BASE_URL = process.env.PW_PROVIDER_BASE_URL || ''
const REQUESTED_MODEL_NAME = process.env.PW_MODEL_NAME || ''
const REQUESTED_EMBEDDING_MODEL_NAME = process.env.PW_EMBEDDING_MODEL_NAME || ''
const PROVIDER_API_KEY = process.env.PW_PROVIDER_API_KEY || ''
const TEST_USER_PASSWORD = process.env.PW_TEST_USER_PASSWORD || 'User123!Pass'

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
  test('register user, configure provider/pricing and run full project/graph/oasis flow', async ({ page, request }) => {
    test.setTimeout(25 * 60 * 1000)

    const testUserEmail = `pw-user-${Date.now()}@example.com`

    await registerTestUserInApi(request, testUserEmail)

    const adminToken = await loginAdminInApi(request)
    const provider = await upsertProviderInAdminApi(request, adminToken)
    const modelSelection = await ensureProviderModelsInAdminApi(request, adminToken, provider)
    await upsertPricingInAdminApi(request, adminToken, modelSelection.model)
    await tuneOasisRuntimeInAdminApi(request, adminToken)
    await topUpUserBalanceInAdminApi(request, adminToken, testUserEmail, 500)
    await login(page, testUserEmail, TEST_USER_PASSWORD)
    const userToken = await getAuthToken(page)

    await createProjectFromDashboard(page)
    await runCreateOperation(page, request, userToken, modelSelection.model)
    await runOntologyToGraphToOasisPipeline(
      page,
      request,
      userToken,
      modelSelection.model,
      modelSelection.embeddingModel
    )
    await runContinueOperation(page, request, userToken, modelSelection.model)
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
  await page.getByPlaceholder('Enter your password').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
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
    throw new Error(
      'No embedding model available. Add embedding model in WebUI or set PW_EMBEDDING_MODEL_NAME for this e2e run.'
    )
  }

  if (!latest.embedding_models.includes(embeddingModel)) {
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

async function tuneOasisRuntimeInAdminApi(request: APIRequestContext, token: string) {
  const current = await adminApi<Record<string, unknown>>(request, token, 'GET', '/api/admin/oasis-config')
  await adminApi(request, token, 'PUT', '/api/admin/oasis-config', {
    ...current,
    llm_request_timeout_seconds: 180,
    llm_retry_count: 2,
    llm_retry_interval_seconds: 1,
    llm_prefer_stream: false,
    llm_stream_fallback_nonstream: true,
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

async function createProjectFromDashboard(page: Page) {
  e2eLog('Create project: open projects page')
  await page.goto('/projects')
  await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /New Project|Create Project/i }).first().click()
  await page.getByPlaceholder('Project title').fill(`E2E Full Flow ${Date.now()}`)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+$/)
  e2eLog('Create project: waiting for project workspace shell')
  await expect(page.getByRole('tab', { name: /Graph \+ RAG/i })).toBeVisible({ timeout: 60000 })
  await expect(page.getByRole('tab', { name: /AI Create/i })).toBeVisible({ timeout: 60000 })
  await expect(page.getByRole('tab', { name: /Scenario Sim/i })).toBeVisible({ timeout: 60000 })
}

async function openTab(page: Page, tabName: RegExp) {
  const tab = page.getByRole('tab', { name: tabName })
  if (await tab.count()) {
    const firstTab = tab.first()
    await expect(firstTab).toBeVisible({ timeout: 60000 })
    await firstTab.click({ timeout: 20000 })
    return
  }
  const fallbackButton = page.getByRole('button', { name: tabName }).first()
  await expect(fallbackButton).toBeVisible({ timeout: 60000 })
  await fallbackButton.click({ timeout: 20000 })
}

async function runCreateOperation(page: Page, request: APIRequestContext, token: string, model: string) {
  e2eLog(`AI Create: start with model ${model}`)
  e2eLog('AI Create: opening tab')
  await openTab(page, /AI Create/i)
  e2eLog('AI Create: tab open')
  e2eLog(`AI Create: selecting model ${model}`)
  await selectModelByLabel(page, 'Operation Model', model)
  e2eLog('AI Create: model selected')
  e2eLog('AI Create: filling prompt')
  await page.getByPlaceholder('Describe theme, style, setting, and any must-have elements.').fill(
    'Write a story about coastal public transit coordination, with competing stakeholders and risk response.'
  )
  e2eLog('AI Create: filling outline')
  await page.getByPlaceholder('Generated outline will appear here. You can edit before drafting.').fill(
    '1. Rush-hour congestion escalates into a public issue.\n2. Operators publish a pilot plan and explain resource limits.\n3. Community representatives push for coordination and accountability.'
  )
  e2eLog('AI Create: clicking draft generation')
  await clickAndWait(page.getByRole('button', { name: /Generate Draft From Outline/i }))
  e2eLog('AI Create: waiting for operation completion via API')
  await waitForOperationStatus(page, request, token, 'CREATE', 300000)
  e2eLog('AI Create: operation completed')
}

async function runContinueOperation(page: Page, request: APIRequestContext, token: string, model: string) {
  e2eLog(`AI Continue: start with model ${model}`)
  await openTab(page, /AI Create/i)
  e2eLog('AI Continue: clicking continue mode')
  await clickAndWait(page.getByRole('button', { name: 'Continue' }))
  await selectModelByLabel(page, 'Operation Model', model)
  await page.getByPlaceholder('Describe what should happen next and any writing constraints.').fill(
    'Continue the story with risk handling, negotiation, and a realistic consensus-building outcome.'
  )
  await page.getByPlaceholder('Continuation outline and checks from graph analysis will appear here.').fill(
    '1. The community and operators hold a joint coordination meeting.\n2. The main disagreements are quantified into measurable checkpoints.\n3. After rollout, feedback gradually turns positive.'
  )
  await clickAndWait(page.getByRole('button', { name: /Run Continue/i }))
  e2eLog('AI Continue: waiting for operation completion via API')
  await waitForOperationStatus(page, request, token, 'CONTINUE', 300000)
  e2eLog('AI Continue: operation completed')
}

async function runOntologyToGraphToOasisPipeline(
  page: Page,
  request: APIRequestContext,
  token: string,
  model: string,
  embeddingModel: string
) {
  await openTab(page, /Graph \+ RAG/i)
  await expect(page.getByRole('button', { name: 'Generate Ontology' })).toBeEnabled({ timeout: 60000 })

  await selectModelByLabel(page, 'Ontology Model', model)
  await selectModelByLabel(page, 'Graph Build Model', model)
  await selectModelByLabel(page, 'Embedding Model', embeddingModel)

  await clickAndWait(page.getByRole('button', { name: 'Generate Ontology' }))
  await expect(page.getByText('Ontology ready')).toBeVisible({ timeout: 300000 })

  e2eLog('Graph pipeline: build knowledge graph')
  const buildGraphButtons = page.getByRole('button', { name: /Build Knowledge Graph/i })
  e2eLog(`Graph pipeline: build button count ${await buildGraphButtons.count()}`)
  const buildGraphButton = buildGraphButtons.first()
  e2eLog(`Graph pipeline: build button text ${(await buildGraphButton.textContent())?.trim() || '<empty>'}`)
  e2eLog(`Graph pipeline: build button disabled attr ${String(await buildGraphButton.getAttribute('disabled'))}`)
  await expect(buildGraphButton).toBeEnabled({ timeout: 60000 })
  await buildGraphButton.scrollIntoViewIfNeeded()
  e2eLog('Graph pipeline: build button scrolled into view')
  const buildButtonHitTest = await buildGraphButton.evaluate((el) => {
    const rect = el.getBoundingClientRect()
    const x = rect.left + rect.width / 2
    const y = rect.top + rect.height / 2
    const top = document.elementFromPoint(x, y)
    return {
      same: !!top && (top === el || el.contains(top)),
      topTag: top?.tagName || null,
      topText: (top?.textContent || '').trim().slice(0, 80),
    }
  })
  e2eLog(`Graph pipeline: build button hit test ${JSON.stringify(buildButtonHitTest)}`)
  e2eLog('Graph pipeline: clicking build button')
  await buildGraphButton.click({ timeout: 20000 })
  e2eLog('Graph pipeline: click returned')
  await waitForGraphReady(page, request, token, 10 * 60 * 1000)
  e2eLog('Graph pipeline: graph is ready')

  e2eLog('Scenario pipeline: open Scenario Sim tab')
  await openTab(page, /Scenario Sim/i)
  await page.getByPlaceholder('Describe the scenario analysis focus').fill('Focus on behavior shifts, risk inflection points, and propagation paths.')
  await selectModelByLabel(page, 'Analysis Model', model)
  await selectModelByLabel(page, 'Execution Model', model)
  await selectModelByLabel(page, 'Report Model', model)

  e2eLog('Scenario pipeline: generate analysis')
  await clickAndWait(page.getByRole('button', { name: 'Generate Scenario Analysis' }))
  await expect(page.getByText('Scenario analysis is ready. Guidance and analysis profiles are now available for continuation workflows.'))
    .toBeVisible({ timeout: 300000 })

  e2eLog('Scenario pipeline: prepare runtime package')
  await clickAndWait(page.getByRole('button', { name: 'Prepare Runtime Package' }))
  await expect(page.getByText('Runtime Package:')).toBeVisible({ timeout: 300000 })

  e2eLog('Scenario pipeline: execute run')
  await clickAndWait(page.getByRole('button', { name: 'Execute Scenario Run' }))
  await expect(page.getByText('Run:')).toBeVisible({ timeout: 300000 })

  e2eLog('Scenario pipeline: generate report')
  await clickAndWait(page.getByRole('button', { name: 'Generate Analysis Report' }))
  await expect(page.getByText(/^Report: report_/).first()).toBeVisible({ timeout: 300000 })
}

async function waitForOperationStatus(
  page: Page,
  request: APIRequestContext,
  token: string,
  type: 'CREATE' | 'CONTINUE',
  timeoutMs: number
) {
  const projectId = await currentProjectId(page)
  await expect
    .poll(
      async () => {
        const response = await request.fetch(`/api/projects/${projectId}/operations`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok()) return `error:${response.status()}`
        const payload = (await response.json()) as Array<{ type?: string; status?: string; output?: string | null }>
        const match = payload.find((item) => String(item.type || '').toUpperCase() === type)
        if (!match) return 'missing'
        const status = String(match.status || '').toUpperCase()
        if (status === 'FAILED') return 'FAILED'
        if (status === 'COMPLETED' && String(match.output || '').trim()) return 'COMPLETED'
        return status || 'pending'
      },
      { timeout: timeoutMs, intervals: [1000, 2000, 3000, 5000] }
    )
    .toBe('COMPLETED')
}

async function waitForGraphReady(page: Page, request: APIRequestContext, token: string, timeoutMs: number) {
  e2eLog('Graph pipeline: waiting for graph readiness')
  const projectId = await currentProjectId(page)
  await expect
    .poll(
      async () => {
        const [statusResponse, taskResponse] = await Promise.all([
          request.fetch(`/api/projects/${projectId}/graphs`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          request.fetch(`/api/projects/${projectId}/graphs/tasks?task_type=graph_build&limit=5`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ])
        if (!statusResponse.ok()) return 'error'
        const payload = (await statusResponse.json()) as { status?: string; graph_freshness?: string }

        if (taskResponse.ok()) {
          const taskPayload = (await taskResponse.json()) as {
            tasks?: Array<{ status?: string; error?: string | null; message?: string | null }>
          }
          const latestTask = (taskPayload.tasks || [])[0]
          if (latestTask && String(latestTask.status || '').toLowerCase() === 'failed') {
            return `failed:${String(latestTask.error || latestTask.message || 'Graph build task failed')}`
          }
        }

        if (payload.status !== 'ready') return payload.status || 'pending'
        if (payload.graph_freshness === 'syncing') return 'syncing'
        return 'ready'
      },
      { timeout: timeoutMs, intervals: [1000, 2000, 3000, 5000] }
    )
    .toBe('ready')
}

async function currentProjectId(page: Page): Promise<string> {
  const match = page.url().match(/\/projects\/([^/?#]+)/)
  if (!match || !match[1]) {
    throw new Error(`Cannot resolve project id from URL: ${page.url()}`)
  }
  return match[1]
}

async function selectModelByLabel(page: Page, label: string, model: string) {
  const field = page.getByText(label, { exact: true }).locator('xpath=ancestor::*[.//select][1]').first()
  const select = field.locator('select').first()
  await expect(select).toBeVisible({ timeout: 180000 })
  await expect(select).toBeEnabled({ timeout: 180000 })
  await select.scrollIntoViewIfNeeded()
  await expect
    .poll(async () => select.locator(`option[value="${model}"]`).count(), { timeout: 180000 })
    .toBeGreaterThan(0)
  await select.selectOption({ value: model })
}

async function clickAndWait(locator: Locator) {
  await locator.scrollIntoViewIfNeeded()
  await locator.click()
}

async function logout(page: Page) {
  e2eLog('Logout and cleanup session')
  await page.evaluate(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  })
  await page.context().clearCookies()
  await page.goto('/login')
  await expect(page).toHaveURL(/\/login$/)
}





