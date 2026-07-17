import { expect, test } from '@playwright/test'

const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:4080'
const WEB_BASE = process.env.E2E_WEB_URL || process.env.PW_BASE_URL || 'http://127.0.0.1:3010'

test.describe('Agent workspace UI fixes', () => {
  test('loads new bundle, resize handles, and step preview from API session', async ({ page, request }) => {
    const login = await request.post(`${API_BASE}/api/auth/login`, {
      data: { email: 'admin@example.com', password: 'Admin123!Pass' },
    })
    expect(login.ok()).toBeTruthy()
    const { token } = await login.json()

    const projectsRes = await request.get(`${API_BASE}/api/projects`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(projectsRes.ok()).toBeTruthy()
    const projects = (await projectsRes.json()) as Array<{ id: string }>
    expect(projects.length).toBeGreaterThan(0)
    const projectId = projects[0].id

    const sessionsRes = await request.get(`${API_BASE}/api/projects/${projectId}/agent/sessions`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(sessionsRes.ok()).toBeTruthy()
    const sessions = (await sessionsRes.json()) as Array<{ session_id: string }>
    const sessionId = sessions[0]?.session_id
    expect(sessionId).toBeTruthy()

    let memoryPreview: string | null = null
    for (const s of sessions) {
      const sessionRes = await request.get(`${API_BASE}/api/projects/${projectId}/agent/chat/${s.session_id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!sessionRes.ok()) continue
      const session = await sessionRes.json()
      const memoryStep = (session.steps || []).find(
        (st: { step_type?: string }) => st.step_type === 'store_structured_memory',
      )
      if (memoryStep?.tool_result_preview) {
        memoryPreview = String(memoryStep.tool_result_preview)
        break
      }
    }
    expect(memoryPreview || '').toMatch(/已写入结构化记忆|会话标题/)

    await page.addInitScript((authToken: string) => {
      localStorage.setItem('token', authToken)
      localStorage.setItem('musegraph-locale', 'zh-CN')
    }, token)

    const chunkReq = page.waitForResponse(
      (res) => res.url().includes('/assets/AgentWorkspaceView-') && res.url().endsWith('.js'),
      { timeout: 60_000 },
    )
    await page.goto(`${WEB_BASE}/projects/${projectId}`)
    await page.waitForLoadState('domcontentloaded')
    const chunkRes = await chunkReq
    const chunkBody = await chunkRes.text()
    expect(chunkBody).toMatch(/72px|120px/)
    expect(chunkBody).toContain('resizeSidebar')
    expect(chunkBody).toContain('tool_result_preview')
    expect(chunkBody).toContain('thinking_delta')

    await expect(page.getByTestId('agent-chat-input')).toBeVisible({ timeout: 30_000 })

    const sessionHandle = page.locator('[data-testid="agent-resize-handle"][aria-label="sessions-center"]')
    await expect(sessionHandle).toBeVisible()

    const sidebar = page.getByTestId('agent-session-sidebar')
    const widthBefore = await sidebar.evaluate((el) => el.getBoundingClientRect().width)
    const handleBox = await sessionHandle.boundingBox()
    expect(handleBox).toBeTruthy()
    const midY = handleBox!.y + handleBox!.height / 2
    await page.mouse.move(handleBox!.x + handleBox!.width / 2, midY)
    await page.mouse.down()
    await page.mouse.move(handleBox!.x + 80, midY, { steps: 12 })
    await page.mouse.up()
    await page.waitForTimeout(200)
    const widthAfter = await sidebar.evaluate((el) => el.getBoundingClientRect().width)
    expect(widthAfter).toBeGreaterThan(widthBefore + 15)

    const stepCard = page.locator('.muse-step-card').filter({ hasText: '结构化记忆' }).first()
    if (await stepCard.count()) {
      await expect(stepCard).toBeVisible()
      const chevron = stepCard.locator('.muse-step-chevron')
      if (await chevron.count()) {
        await chevron.click()
      }
    }
  })
})
