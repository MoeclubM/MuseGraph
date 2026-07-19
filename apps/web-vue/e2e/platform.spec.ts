import { expect, test } from '@playwright/test'


test('cookie session, project Agent, prompt template, Git versions, Skill resolution, and XSS safety', async ({ page, context }) => {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const email = `browser-${suffix}@example.com`
  const password = 'Browser-E2E-Password-2026!'

  await page.addInitScript(() => {
    localStorage.setItem('musegraph-locale', 'zh-CN')
  })
  const registrationResponse = page.waitForResponse(
    (response) => response.url().endsWith('/api/auth/register')
      && response.request().method() === 'POST',
  )
  await page.goto('/register')
  await page.locator('input[name="email"]').fill(email)
  await page.locator('input[name="nickname"]').fill('Browser E2E')
  await page.locator('input[name="password"]').fill(password)
  await page.getByRole('button', { name: '创建账户' }).click()
  const registration = await registrationResponse
  expect(registration.status()).toBe(201)
  expect(await registration.json()).not.toHaveProperty('token')
  await expect(page).toHaveURL(/\/dashboard$/)

  const browserStorage = await page.evaluate(() => ({
    token: localStorage.getItem('token'),
    user: localStorage.getItem('user'),
  }))
  expect(browserStorage).toEqual({ token: null, user: null })
  const cookies = await context.cookies()
  const sessionCookie = cookies.find((cookie) => cookie.name === 'musegraph_session')
  expect(sessionCookie?.httpOnly).toBe(true)
  expect(sessionCookie?.sameSite).toBe('Lax')

  await page.goto('/projects')
  await page.getByRole('button', { name: '新建项目' }).click()
  const modal = page.getByRole('dialog')
  await modal.locator('input').nth(0).fill(`Browser platform ${suffix}`)
  await modal.locator('input').nth(1).fill('Real browser platform acceptance')
  const projectResponse = page.waitForResponse(
    (response) => response.url().endsWith('/api/projects')
      && response.request().method() === 'POST',
  )
  await modal.getByRole('button', { name: '创建' }).click()
  expect((await projectResponse).status()).toBe(201)
  await expect(page).toHaveURL(/\/projects\/[^/?#]+$/)
  const projectId = page.url().match(/\/projects\/([^/?#]+)/)?.[1]
  expect(projectId).toBeTruthy()

  await page.goto('/settings/prompt-templates')
  await page.getByPlaceholder('模板名称').fill(`Browser writer ${suffix}`)
  await page.getByPlaceholder('用途说明').fill('Account-owned writer phase template')
  await page.locator('select').selectOption('writer')
  await page.getByPlaceholder(/阶段提示词/).fill(
    '为 {{project_title}} 落实 CreativeBlueprint；目标：{{instruction}}。',
  )
  const templateResponse = page.waitForResponse(
    (response) => response.url().endsWith('/api/users/me/prompt-templates')
      && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '保存' }).click()
  const template = await (await templateResponse).json()

  await page.goto(`/projects/${projectId}/agents`)
  await expect(page.getByRole('heading', { name: '项目 Agents' })).toBeVisible()
  await expect(page.getByText('默认创作 Agent', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '新建 Agent' }).click()
  await page.getByPlaceholder('Agent 名称').fill(`Browser Agent ${suffix}`)
  await page.getByPlaceholder('Agent 的职责与定位').fill('Project-bound browser Agent')
  await page.locator('label').filter({ hasText: '推理强度' }).locator('select').selectOption('high')
  await page.locator('label').filter({ hasText: 'writer' }).locator('select').selectOption(template.id)
  const agentResponse = page.waitForResponse(
    (response) => response.url().endsWith(`/api/projects/${projectId}/agents`)
      && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '保存' }).click()
  expect((await agentResponse).status()).toBe(201)
  const activateResponse = page.waitForResponse(
    (response) => response.url().includes(`/api/projects/${projectId}/agents/`)
      && response.url().endsWith('/activate')
      && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '设为活动 Agent' }).click()
  expect((await activateResponse).status()).toBe(200)
  await expect(page.getByText(`Browser Agent ${suffix}`, { exact: true })).toBeVisible()

  await page.goto(`/projects/${projectId}`)
  const filePath = 'chapters/browser.md'
  await page.getByPlaceholder('drafts/chapter-01.md').fill(filePath)
  const createFileResponse = page.waitForResponse(
    (response) => response.url().includes(`/api/projects/${projectId}/files/manual`)
      && response.request().method() === 'POST',
  )
  await page.getByPlaceholder('drafts/chapter-01.md').press('Enter')
  expect((await createFileResponse).status()).toBe(201)
  const editor = page.locator('aside textarea')
  await expect(editor).toBeVisible()
  await editor.fill('# Browser chapter\n\n<img src=x onerror=window.__musegraph_xss=true>\n\nCookie-only session.')
  const saveResponse = page.waitForResponse(
    (response) => response.url().includes(`/api/projects/${projectId}/files/content`)
      && response.request().method() === 'PUT',
  )
  await page.locator('button:has(svg.lucide-save)').click()
  expect((await saveResponse).status()).toBe(200)
  expect(await page.evaluate(() => (window as Window & { __musegraph_xss?: boolean }).__musegraph_xss)).toBeUndefined()

  await page.getByRole('button', { name: '知识', exact: true }).click()
  await expect(page.getByText(/不可变 Cognee Dataset/)).toBeVisible()
  await expect(page.getByText('0 条记录')).toBeVisible()

  await page.getByRole('button', { name: '版本', exact: true }).click()
  await expect(page.getByText('active', { exact: true }).first()).toBeVisible()
  const restoreButton = page.getByRole('button', { name: '创建恢复审核' }).first()
  await expect(restoreButton).toBeVisible()
  const restoreResponse = page.waitForResponse(
    (response) => response.url().includes(`/api/projects/${projectId}/versions/restore`)
      && response.request().method() === 'POST',
  )
  await restoreButton.click()
  expect((await restoreResponse).status()).toBe(201)
  await expect(page.getByRole('button', { name: '整轮拒绝' })).toBeVisible()
  await expect(page.getByRole('button', { name: '接受并发布' })).toBeVisible()
  await expect(page.getByText('自检报告')).toBeVisible()
  const rejectResponse = page.waitForResponse(
    (response) => response.url().includes('/review')
      && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '整轮拒绝' }).click()
  expect((await rejectResponse).status()).toBe(200)
  await expect(
    page.getByText(`write · rejected · Browser Agent ${suffix} · version-restore`, { exact: true }),
  ).toBeVisible()

  await page.getByTestId('agent-nav-settings').click()
  await expect(page.getByRole('heading', { name: '项目设置' })).toBeVisible()
  const repositoryResponse = page.waitForResponse(
    (response) => response.url().endsWith(`/api/projects/${projectId}/export/repository`)
      && response.request().method() === 'POST',
  )
  const repositoryDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 Git 仓库' }).click()
  expect((await repositoryResponse).status()).toBe(200)
  expect((await repositoryDownload).suggestedFilename()).toContain('-repository.zip')
  await page.getByRole('button', { name: 'Skills' }).click()
  await expect(page.getByRole('heading', { name: '项目 Skills' })).toBeVisible()
  await page.getByPlaceholder('slug').fill('browser-voice')
  await page.getByPlaceholder('名称').fill('Browser Voice')
  await page.getByPlaceholder('说明').fill('Browser-only project Skill')
  await page.getByPlaceholder('运行指令').fill('Write concise, source-grounded prose.')
  const skillResponse = page.waitForResponse(
    (response) => response.url().endsWith(`/api/projects/${projectId}/skills`)
      && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '保存' }).click()
  expect((await skillResponse).status()).toBe(201)
  await page.getByRole('button', { name: /@browser-voice/ }).click()
  const previewResponse = page.waitForResponse(
    (response) => response.url().includes('/skills/resolve/preview')
      && response.request().method() === 'GET',
  )
  await page.getByRole('button', { name: '预览解析' }).click()
  expect((await previewResponse).status()).toBe(200)
  await expect(page.locator('pre').filter({ hasText: '"source": "project"' })).toBeVisible()

  await page.reload()
  await expect(page.getByRole('heading', { name: '项目 Skills' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
})
