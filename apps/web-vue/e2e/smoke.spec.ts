import { expect, test, type Page } from '@playwright/test'

const now = '2026-02-24T00:00:00Z'

const regularUser = {
  id: 'user-1',
  email: 'user@example.com',
  nickname: 'User',
  avatar: null,
  balance: 0,
  is_admin: false,
  group_id: null,
  status: 'ACTIVE',
  created_at: now,
}

const adminUser = {
  ...regularUser,
  id: 'admin-1',
  email: 'admin@example.com',
  nickname: 'Admin',
  is_admin: true,
}

async function fulfillJson(route: any, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function mockProjectApis(page: Page) {
  await page.route('**/api/projects', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, [])
      return
    }
    await fulfillJson(route, {
      id: 'project-1',
      user_id: regularUser.id,
      title: 'New Project',
      description: null,
      content: null,
      created_at: now,
      updated_at: now,
    })
  })
}

async function mockAdminApis(page: Page) {
  await page.route('**/api/auth/me', (route) => fulfillJson(route, adminUser))
  await page.route('**/api/admin/stats', (route) =>
    fulfillJson(route, {
      total_users: 1,
      total_projects: 0,
      total_operations: 0,
      total_revenue: 0,
      daily_active_users: 1,
    }))
  await page.route('**/api/admin/users**', (route) =>
    fulfillJson(route, {
      users: [adminUser],
      total: 1,
      page: 1,
      page_size: 20,
    }))
  await page.route('**/api/admin/providers', (route) =>
    fulfillJson(route, [{
      id: 'provider-1',
      name: 'Main Provider',
      provider: 'openai_compatible',
      base_url: 'https://example.com/v1',
      models: ['MiniMax-M2.5'],
      is_active: true,
      priority: 1,
    }]))
  await page.route('**/api/admin/payment-adapter-types', (route) =>
    fulfillJson(route, {
      types: [{ id: 'epay', label: 'EPay', description: 'Epay gateway' }],
    }))
  await page.route('**/api/admin/payment-adapters', (route) =>
    fulfillJson(route, { adapters: [] }))
  await page.route('**/api/admin/pricing', (route) => fulfillJson(route, []))
  await page.route('**/api/admin/llm-runtime-config', (route) =>
    fulfillJson(route, {
      llm_request_timeout_seconds: 180,
      llm_retry_count: 4,
      llm_retry_interval_seconds: 2,
      llm_prefer_stream: true,
      llm_stream_fallback_nonstream: true,
      llm_fallback_model: '',
      llm_openai_api_style: 'responses',
      llm_reasoning_effort: 'model_default',
      llm_task_concurrency: 4,
      llm_model_default_concurrency: 8,
      llm_model_concurrency_overrides: {},
    }))
  await page.route('**/api/admin/tasks**', (route) =>
    fulfillJson(route, { tasks: [], total: 0, limit: 50 }))
}

test('login -> dashboard smoke flow', async ({ page }) => {
  await mockProjectApis(page)
  await page.route('**/api/auth/login', (route) =>
    fulfillJson(route, { token: 'e2e-token', user: regularUser }))

  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill('user@example.com')
  await page.getByPlaceholder('输入密码').fill('password123')
  await page.getByRole('button', { name: '登录' }).click()

  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { name: '仪表盘' })).toBeVisible()
  await expect(page.getByText('暂无项目').first()).toBeVisible()
})

test('admin providers tab has no model-management controls', async ({ page }) => {
  await mockAdminApis(page)
  await page.addInitScript((payload) => {
    localStorage.setItem('token', payload.token)
    localStorage.setItem('user', JSON.stringify(payload.user))
  }, { token: 'admin-token', user: adminUser })

  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: '运营与配置' })).toBeVisible()

  await page.getByRole('button', { name: 'AI 服务商' }).click()
  await expect(page.getByRole('heading', { name: 'AI 服务商' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '名称' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '类型' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Models' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Discover' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Import' })).toHaveCount(0)

  await page.getByRole('button', { name: '模型与定价' }).click()
  await expect(page.getByRole('heading', { name: '模型与定价' })).toBeVisible()
  await expect(page.getByRole('button', { name: '发现' })).toBeVisible()
  await expect(page.getByRole('button', { name: '导入并保存' })).toBeVisible()
})
