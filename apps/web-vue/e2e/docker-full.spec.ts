import { expect, test, type Locator, type Page } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const ADMIN_EMAIL = process.env.PW_ADMIN_EMAIL || 'admin@example.com'
const ADMIN_PASSWORD = process.env.PW_ADMIN_PASSWORD || 'Admin123!Pass'
const PROVIDER_NAME = process.env.PW_PROVIDER_NAME || 'PW OpenAI-Compatible'
const PROVIDER_BASE_URL = process.env.PW_PROVIDER_BASE_URL || 'https://newapi.telecom.moe/v1'
const MODEL_NAME = process.env.PW_MODEL_NAME || 'MiniMax-M2.5'
const PROVIDER_API_KEY = process.env.PW_PROVIDER_API_KEY || ''
const TEST_USER_PASSWORD = process.env.PW_TEST_USER_PASSWORD || 'User123!Pass'

const operationDocPath = path.join(__dirname, 'fixtures', 'operation-input.txt')

test.describe('Docker Full Flow (No Mock)', () => {
  test('register user, configure model pricing, recharge and run full project/graph/oasis flow', async ({ page }) => {
    test.setTimeout(20 * 60 * 1000)
    if (!PROVIDER_API_KEY) {
      throw new Error('PW_PROVIDER_API_KEY is required for real provider configuration')
    }
    const testUserEmail = `pw-user-${Date.now()}@example.com`

    await registerTestUser(page, testUserEmail)
    await loginAsAdmin(page)
    await upsertProviderInAdmin(page)
    await ensureProviderModelInAdmin(page)
    await upsertPricingInAdmin(page)
    await topUpUserBalanceInAdmin(page, testUserEmail, 50)
    await logout(page)

    await login(page, testUserEmail, TEST_USER_PASSWORD)

    await createProjectFromDashboard(page)
    await runCreateOperation(page)
    await runContinueOperationWithUpload(page)

    await runOntologyToGraphToOasisPipeline(page)
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

async function upsertProviderInAdmin(page: Page) {
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Admin Panel' })).toBeVisible()

  await page.getByRole('button', { name: 'providers' }).click()
  await expect(page.getByRole('heading', { name: 'Providers' })).toBeVisible()

  const row = providerRow(page)
  if (await row.count()) {
    await row.first().getByRole('button', { name: 'Edit' }).click()
  } else {
    await page.getByRole('button', { name: 'New' }).click()
    await page.getByPlaceholder('Name').fill(PROVIDER_NAME)
  }

  const form = page.locator('div').filter({ has: page.getByPlaceholder('API key') }).first()
  await form.locator('select').first().selectOption('openai_compatible')
  await form.getByPlaceholder('API key').fill(PROVIDER_API_KEY)
  await form.getByPlaceholder('Base URL').fill(PROVIDER_BASE_URL)
  await form.getByPlaceholder('Priority').fill('100')
  await form.getByRole('button', { name: 'Save' }).click()

  await expect(providerRow(page).first()).toBeVisible()
}

async function ensureProviderModelInAdmin(page: Page) {
  await page.getByRole('button', { name: 'models' }).click()
  await expect(page.getByRole('heading', { name: 'Models' })).toBeVisible()

  const providerSelect = page.locator('select').first()
  await providerSelect.selectOption({ label: PROVIDER_NAME })

  const modelChip = page.locator('span', { hasText: MODEL_NAME }).first()
  if (await modelChip.count()) {
    return
  }

  const manualInput = page.getByPlaceholder('model')
  await manualInput.fill(MODEL_NAME)
  const addManualButton = manualInput.locator('xpath=following-sibling::button[1]')
  await addManualButton.click()

  await expect(page.locator('span', { hasText: MODEL_NAME }).first()).toBeVisible()
}

async function upsertPricingInAdmin(page: Page) {
  await page.getByRole('button', { name: 'models' }).click()
  const row = page.locator('tr', { hasText: MODEL_NAME }).first()
  await expect(row).toBeVisible()
  await row.getByRole('button').click()

  const form = page.locator('div').filter({ has: page.getByPlaceholder('Token Unit (e.g. 1000000)') }).first()
  await form.getByPlaceholder('Input Price').fill('1.1')
  await form.getByPlaceholder('Output Price').fill('4.4')
  await form.getByPlaceholder('Token Unit (e.g. 1000000)').fill('1000000')
  await form.getByRole('button', { name: 'Save' }).click()
  await expect(page.locator('tr', { hasText: MODEL_NAME }).first().getByText('/ 1,000,000 tokens')).toBeVisible()
}

async function topUpUserBalanceInAdmin(page: Page, email: string, amount: number) {
  await page.getByRole('button', { name: 'users' }).click()
  await page.getByPlaceholder('Search by email / nickname').fill(email)
  await page.getByRole('button', { name: 'Search' }).click()

  const row = page.locator('tr', { hasText: email }).first()
  await expect(row).toBeVisible()
  await row.getByPlaceholder('+金额').fill(String(amount))
  await row.getByRole('button', { name: '加余额' }).click()
}

async function createProjectFromDashboard(page: Page) {
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await page.getByRole('button', { name: 'New Project' }).nth(1).click()
  await page.getByPlaceholder('Project title').fill(`E2E Full Flow ${Date.now()}`)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+$/)
}

async function runCreateOperation(page: Page) {
  await page.getByPlaceholder('Write chapter content here...').fill(
    '这是一段用于真实端到端测试的基础创作信息，主题是城市公共交通与社区协作。'
  )
  await selectModelByLabel(page, 'Operation Model', MODEL_NAME)
  await page.getByRole('button', { name: 'Run Create' }).click()
  await expect(page.getByText('COMPLETED').first()).toBeVisible({ timeout: 240000 })
}

async function runContinueOperationWithUpload(page: Page) {
  await page.getByRole('button', { name: 'Continue' }).click()
  await selectModelByLabel(page, 'Operation Model', MODEL_NAME)
  await page.locator('input[type="file"][accept=".txt,.md,.docx,.pdf"]').setInputFiles(operationDocPath)
  await page.getByRole('button', { name: 'Upload & Run Continue' }).click()
  await expect(page.getByText('COMPLETED').first()).toBeVisible({ timeout: 240000 })
}

async function runOntologyToGraphToOasisPipeline(page: Page) {
  await page.getByRole('button', { name: /Knowledge Graph/i }).click()
  await page.getByRole('button', { name: 'Editor Content' }).click()
  await expect(page.getByRole('button', { name: 'Generate Ontology' })).toBeEnabled({ timeout: 30000 })

  await page.getByPlaceholder('Describe your ontology/simulation focus').fill('关注群体行为演化、风险节点和传播路径。')
  await selectModelByLabel(page, 'Ontology Model', MODEL_NAME)
  await selectModelByLabel(page, 'Graph Build Model', MODEL_NAME)
  await selectModelByLabel(page, 'OASIS Analysis Model', MODEL_NAME)
  await selectModelByLabel(page, 'OASIS Simulation Model', MODEL_NAME)
  await selectModelByLabel(page, 'OASIS Report Model', MODEL_NAME)

  await clickAndWait(page.getByRole('button', { name: 'Generate Ontology' }))
  await expect(page.getByText('Ontology ready')).toBeVisible({ timeout: 300000 })

  await clickAndWait(page.getByRole('button', { name: 'Build Knowledge Graph' }))
  await expect(page.getByText('Graph build completed')).toBeVisible({ timeout: 600000 })
  await expect(page.getByRole('button', { name: 'Run OASIS Analysis' })).toBeEnabled({ timeout: 300000 })

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

async function selectModelByLabel(page: Page, label: string, model: string) {
  const select = page.locator('label', { hasText: label }).locator('xpath=following-sibling::select').first()
  await select.scrollIntoViewIfNeeded()
  await expect
    .poll(async () => select.locator(`option[value="${model}"]`).count(), { timeout: 180000 })
    .toBeGreaterThan(0)
  await select.selectOption({ label: model })
}

async function clickAndWait(locator: Locator) {
  await locator.scrollIntoViewIfNeeded()
  await locator.click()
}

function providerRow(page: Page): Locator {
  return page.locator('tr', { hasText: PROVIDER_NAME })
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
