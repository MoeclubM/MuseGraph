import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test'

const ADMIN_EMAIL = process.env.PW_ADMIN_EMAIL || 'admin@example.com'
const ADMIN_PASSWORD = process.env.PW_ADMIN_PASSWORD || 'Admin123!Pass'
const PROVIDER_NAME = process.env.PW_PROVIDER_NAME || 'PW OpenAI-Compatible'
const PROVIDER_BASE_URL = process.env.PW_PROVIDER_BASE_URL || ''
const REQUESTED_MODEL_NAME = process.env.PW_MODEL_NAME || ''
const REQUESTED_EMBEDDING_MODEL_NAME = process.env.PW_EMBEDDING_MODEL_NAME || ''
const PROVIDER_API_KEY = process.env.PW_PROVIDER_API_KEY || ''
const TEST_USER_PASSWORD = process.env.PW_TEST_USER_PASSWORD || 'User123!Pass'

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

    await registerTestUser(page, testUserEmail)

    await loginAsAdmin(page)
    const adminToken = await getAuthToken(page)
    const provider = await upsertProviderInAdminApi(request, adminToken)
    const modelSelection = await ensureProviderModelsInAdminApi(request, adminToken, provider)
    await upsertPricingInAdminApi(request, adminToken, modelSelection.model)
    await tuneOasisRuntimeInAdminApi(request, adminToken)
    await topUpUserBalanceInAdminApi(request, adminToken, testUserEmail, 500)
    await logout(page)

    await login(page, testUserEmail, TEST_USER_PASSWORD)
    const userToken = await getAuthToken(page)

    await createProjectFromDashboard(page)
    await runCreateOperation(page, modelSelection.model)
    await runOntologyToGraphToOasisPipeline(
      page,
      request,
      userToken,
      modelSelection.model,
      modelSelection.embeddingModel
    )
    await runContinueOperation(page, modelSelection.model)
  })
})

async function loginAsAdmin(page: Page) {
  await login(page, ADMIN_EMAIL, ADMIN_PASSWORD)
}

async function login(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('Enter your password').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

async function registerTestUser(page: Page, email: string) {
  await page.goto('/register')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('Display name').fill('PW Test User')
  await page.getByPlaceholder('At least 6 characters').fill(TEST_USER_PASSWORD)
  await page.getByRole('button', { name: 'Create Account' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await logout(page)
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
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await page.getByRole('button', { name: /New Project|Create Project/i }).first().click()
  await page.getByPlaceholder('Project title').fill(`E2E Full Flow ${Date.now()}`)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+$/)
}

async function openTab(page: Page, tabName: RegExp) {
  const tab = page.getByRole('tab', { name: tabName })
  if (await tab.count()) {
    await tab.first().click()
    return
  }
  await page.getByRole('button', { name: tabName }).first().click()
}

async function runCreateOperation(page: Page, model: string) {
  await openTab(page, /AI Create/i)
  await selectModelByLabel(page, 'Operation Model', model)
  await page.getByPlaceholder('Describe theme, style, setting, and any must-have elements.').fill(
    '写一个发生在沿海城市的公共交通协同治理故事，包含多方博弈与风险应对。'
  )
  await page.getByPlaceholder('Generated outline will appear here. You can edit before drafting.').fill(
    '1. 高峰拥堵升级并引发舆论关注。\n2. 管理方发布试点方案并解释资源约束。\n3. 社区代表提出改进诉求并参与协同。'
  )
  await clickAndWait(page.getByRole('button', { name: /Generate Draft From Outline/i }))
  await expect(page.getByText('COMPLETED').first()).toBeVisible({ timeout: 300000 })
}

async function runContinueOperation(page: Page, model: string) {
  await openTab(page, /AI Create/i)
  await clickAndWait(page.getByRole('button', { name: 'Continue' }))
  await selectModelByLabel(page, 'Operation Model', model)
  await page.getByPlaceholder('Describe what should happen next and any writing constraints.').fill(
    '继续写后续演化，突出风险处置与共识形成，保持叙事一致。'
  )
  await page.getByPlaceholder('Continuation outline and checks from graph analysis will appear here.').fill(
    '1. 社区与运营方召开联合协调会。\n2. 争议点被量化并给出阶段性指标。\n3. 行动计划上线后反馈逐步转正。'
  )
  await clickAndWait(page.getByRole('button', { name: /Run Continue/i }))
  await expect(page.getByText('COMPLETED').first()).toBeVisible({ timeout: 300000 })
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

  await clickAndWait(page.getByRole('button', { name: /Build Knowledge Graph/i }))
  await waitForGraphReady(page, request, token, 10 * 60 * 1000)

  await openTab(page, /OASIS Sim/i)
  await page.getByPlaceholder('Enter OASIS analysis focus').fill('关注群体行为演化、风险节点和传播路径。')
  await selectModelByLabel(page, 'OASIS Analysis Model', model)
  await selectModelByLabel(page, 'OASIS Simulation Model', model)
  await selectModelByLabel(page, 'OASIS Report Model', model)

  await clickAndWait(page.getByRole('button', { name: 'Run OASIS Analysis' }))
  await expect(page.getByText('OASIS summary ready. Guidance and agent profiles are now used by continuation generation.'))
    .toBeVisible({ timeout: 300000 })

  await clickAndWait(page.getByRole('button', { name: 'Prepare OASIS Package (Task)' }))
  await expect(page.getByText('Simulation Package:')).toBeVisible({ timeout: 300000 })

  await clickAndWait(page.getByRole('button', { name: 'Run OASIS Simulation (Task)' }))
  await expect(page.getByText('Run:')).toBeVisible({ timeout: 300000 })

  await clickAndWait(page.getByRole('button', { name: 'Generate OASIS Report (Task)' }))
  await expect(page.getByText('Report:')).toBeVisible({ timeout: 300000 })
}

async function waitForGraphReady(page: Page, request: APIRequestContext, token: string, timeoutMs: number) {
  const projectId = await currentProjectId(page)
  await expect
    .poll(
      async () => {
        const response = await request.fetch(`/api/projects/${projectId}/graphs`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok()) return 'error'
        const payload = (await response.json()) as { status?: string; graph_freshness?: string }
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
  const select = page.locator('label', { hasText: label }).locator('xpath=following-sibling::select').first()
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
  await page.evaluate(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  })
  await page.context().clearCookies()
  await page.goto('/login')
  await expect(page).toHaveURL(/\/login$/)
}
