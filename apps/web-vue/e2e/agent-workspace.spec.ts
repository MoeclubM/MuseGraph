import { expect, test } from '@playwright/test'

const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:4080'
const WEB_BASE = process.env.E2E_WEB_URL || 'http://127.0.0.1:3010'

test.describe('Agent workspace layout', () => {
  test('shows three-panel agent workspace with session sidebar', async ({ page, request }) => {
    const login = await request.post(`${API_BASE}/api/auth/login`, {
      data: { email: 'admin@example.com', password: 'Admin123!Pass' },
    })
    expect(login.ok()).toBeTruthy()
    const { token } = await login.json()

    const projectRes = await request.post(`${API_BASE}/api/projects`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { title: `E2E Agent UI ${Date.now()}`, description: 'layout test' },
    })
    expect(projectRes.ok()).toBeTruthy()
    const project = await projectRes.json()

    await page.addInitScript((authToken: string) => {
      localStorage.setItem('token', authToken)
      localStorage.setItem('musegraph-locale', 'zh-CN')
    }, token)

    await page.goto(`${WEB_BASE}/projects/${project.id}`)
    await page.waitForLoadState('networkidle')

    await expect(page.getByText('智能体')).toBeVisible()
    await expect(page.getByTestId('agent-new-session')).toBeVisible()
    await expect(page.getByTestId('agent-activity-bar')).toBeVisible()
    await expect(page.getByTestId('agent-activity-editor')).toBeVisible()
    await expect(page.getByTestId('agent-activity-versions')).toBeVisible()
    await expect(page.getByTestId('agent-activity-add')).toBeVisible()
    await expect(page.getByTestId('agent-file-explorer')).toBeVisible()
    await expect(page.getByTestId('agent-chat-input')).toBeVisible({ timeout: 15000 })
  })
})
