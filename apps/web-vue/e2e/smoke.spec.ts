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
      graph_id: null,
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
  await page.route('**/api/admin/groups', (route) =>
    fulfillJson(route, [{ id: 'group-1', name: 'default', description: 'Default group' }]))
  await page.route('**/api/admin/plans', (route) => fulfillJson(route, []))
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
  await page.route('**/api/admin/payment-config', (route) =>
    fulfillJson(route, {
      enabled: false,
      url: '',
      pid: '',
      key: '',
      has_key: false,
      payment_type: 'alipay',
      notify_url: '',
      return_url: '',
    }))
  await page.route('**/api/admin/model-groups', (route) => fulfillJson(route, []))
}

test('login -> dashboard smoke flow', async ({ page }) => {
  await mockProjectApis(page)
  await page.route('**/api/auth/login', (route) =>
    fulfillJson(route, { token: 'e2e-token', user: regularUser }))

  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill('user@example.com')
  await page.getByPlaceholder('Enter your password').fill('password123')
  await page.getByRole('button', { name: 'Sign In' }).click()

  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await expect(page.getByText('No projects yet').first()).toBeVisible()
})

test('admin providers tab has no model-management controls', async ({ page }) => {
  await mockAdminApis(page)
  await page.addInitScript((payload) => {
    localStorage.setItem('token', payload.token)
    localStorage.setItem('user', JSON.stringify(payload.user))
  }, { token: 'admin-token', user: adminUser })

  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Admin Panel' })).toBeVisible()

  await page.getByRole('button', { name: 'providers' }).click()
  await expect(page.getByRole('heading', { name: 'Providers' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Name' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Type' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Models' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Discover' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Import' })).toHaveCount(0)

  await page.getByRole('button', { name: 'models' }).click()
  await expect(page.getByRole('heading', { name: 'Models' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Discover' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Import' })).toBeVisible()
})
