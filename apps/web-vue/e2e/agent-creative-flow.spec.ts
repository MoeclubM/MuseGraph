import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:3010'
const WEB_BASE = process.env.E2E_WEB_URL || process.env.PW_BASE_URL || 'http://127.0.0.1:3010'
const ADMIN_EMAIL = process.env.PW_ADMIN_EMAIL || 'admin@example.com'
const ADMIN_PASSWORD = process.env.PW_ADMIN_PASSWORD || 'Admin123!Pass'
const AGENT_MODEL = process.env.PW_AGENT_MODEL || ''
const AGENT_POLL_MS = Number(process.env.PW_AGENT_POLL_MS || 5000)
const AGENT_TIMEOUT_MS = Number(process.env.PW_AGENT_TIMEOUT_MS || 20 * 60 * 1000)

const SAMPLE_NOVEL = `《星港余烬》节选

公元2387年，人类在比邻星轨道建成了最后一座深空港口"曦环"。港口调度官林澜在值班夜发现一条未知量子信标，频率与二十年前失踪的探险舰"长夜号"一致。

信标解码后只有一句话："不要靠近日冕层。"林澜将情报同步给港口AI"赫斯提"，却收到相互矛盾的航行建议。维修工周原在废弃舱段找到长夜号船员陈默的私人日志，日志显示他们并非失踪，而是在尝试封印一种会吞噬光子的微观结构。

与此同时，港口商业代表艾琳坚持提前启动跃迁窗口，否则将损失三千万信用点。林澜必须在六小时内决定是否推迟跃迁、是否公开日志，以及是否相信一个已经"死去"的船员留下的警告。`

function log(message: string) {
  console.log(`[Agent E2E] ${message}`)
}

async function waitForApiReady(request: APIRequestContext, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs
  let lastError = 'unknown'
  const healthPath = '/api/health'
  while (Date.now() < deadline) {
    try {
      const response = await request.get(`${API_BASE}${healthPath}`, { timeout: 8000 })
      if (response.ok()) {
        log(`API ready at ${API_BASE}`)
        return
      }
      lastError = `status ${response.status()}`
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error)
    }
    await new Promise((r) => setTimeout(r, 3000))
  }
  throw new Error(`API not ready at ${API_BASE} (${lastError})`)
}

async function loginApi(request: APIRequestContext): Promise<string> {
  const response = await request.post(`${API_BASE}/api/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  })
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  return payload.token as string
}

async function resolveAgentModel(request: APIRequestContext, token: string): Promise<string> {
  if (AGENT_MODEL) return AGENT_MODEL
  const response = await request.get(`${API_BASE}/api/ai/models`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.ok()).toBeTruthy()
  const payload = await response.json() as { models?: Array<{ id: string }> }
  const ids = (payload.models || []).map((m) => m.id)
  const preferred = ids.find((id) => /mimo/i.test(id))
    || ids.find((id) => /gpt-4o-mini/i.test(id))
    || ids[0]
  if (!preferred) {
    throw new Error('No AI models available for agent E2E')
  }
  log(`Using model: ${preferred}`)
  return preferred
}

async function createProject(request: APIRequestContext, token: string, title: string) {
  const response = await request.post(`${API_BASE}/api/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title, description: 'Agent creative flow E2E' },
  })
  expect(response.ok()).toBeTruthy()
  return await response.json() as { id: string }
}

async function importNovelChapter(
  request: APIRequestContext,
  token: string,
  projectId: string,
  title: string,
  content: string,
) {
  const response = await request.post(`${API_BASE}/api/projects/${projectId}/chapters`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title, content },
  })
  expect(response.ok()).toBeTruthy()
}

async function setAgentModel(
  request: APIRequestContext,
  token: string,
  projectId: string,
  model: string,
) {
  const getRes = await request.get(`${API_BASE}/api/projects/${projectId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(getRes.ok()).toBeTruthy()
  const project = await getRes.json() as { component_models?: Record<string, string> }
  const componentModels = {
    ...(project.component_models || {}),
    operation_agent_task: model,
    memory_build: model,
    memory_embedding: process.env.PW_EMBEDDING_MODEL || 'Qwen3-Embedding-0.6B',
    memory_reranker: process.env.PW_RERANKER_MODEL || 'Qwen3-Reranker-0.6B',
  }
  const putRes = await request.put(`${API_BASE}/api/projects/${projectId}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { component_models: componentModels },
  })
  expect(putRes.ok()).toBeTruthy()
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
  let consecutivePollErrors = 0
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, AGENT_POLL_MS))
    let response: Awaited<ReturnType<APIRequestContext['get']>>
    try {
      response = await request.get(
        `${API_BASE}/api/projects/${projectId}/agent/chat/${sessionId}`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
    } catch (error) {
      // Transient socket drops happen under heavy server load (WSL2 port
      // forwarding); only fail after several consecutive errors.
      consecutivePollErrors += 1
      log(`session ${sessionId}: poll error #${consecutivePollErrors}: ${String(error)}`)
      if (consecutivePollErrors >= 5) {
        throw error
      }
      continue
    }
    consecutivePollErrors = 0
    expect(response.ok()).toBeTruthy()
    const session = await response.json() as {
      status?: string
      steps?: unknown[]
      messages?: Array<{ role: string; content?: string }>
      plan?: Record<string, unknown>
      updated_at?: string
    }
    lastStatus = String(session.status || '')
    log(
      `session ${sessionId}: status=${lastStatus}, steps=${session.steps?.length || 0}, `
      + `msgs=${session.messages?.length || 0}, updated_at=${session.updated_at || 'n/a'}`,
    )
    if (['completed', 'failed', 'partial'].includes(lastStatus)) {
      return session
    }
  }
  throw new Error(`Agent session timed out (last status: ${lastStatus})`)
}

async function openProjectWorkspace(page: Page, token: string, projectId: string) {
  await page.addInitScript((authToken: string) => {
    localStorage.setItem('token', authToken)
  }, token)
  await page.goto(`${WEB_BASE}/projects/${projectId}`)
  await page.waitForLoadState('domcontentloaded')
  await expect(page.getByTestId('agent-chat-input')).toBeVisible({ timeout: 30000 })
}

async function startAgentChatApi(
  request: APIRequestContext,
  token: string,
  projectId: string,
  message: string,
  model: string,
): Promise<string> {
  const response = await request.post(`${API_BASE}/api/projects/${projectId}/agent/chat`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { message, model },
  })
  expect(response.status()).toBe(202)
  const payload = await response.json() as { session_id: string }
  return payload.session_id
}

async function sendAgentMessage(page: Page, message: string, model?: string): Promise<string> {
  const textarea = page.getByTestId('agent-chat-input')
  await textarea.fill(message)
  if (model) {
    const select = page.locator('select').first()
    if (await select.count()) {
      await select.selectOption(model)
    }
  }
  const chatResponse = page.waitForResponse(
    (res) => res.url().includes('/agent/chat') && res.request().method() === 'POST' && res.status() === 202,
    { timeout: 30000 },
  )
  await page.getByTestId('agent-send-button').click()
  const response = await chatResponse
  const payload = await response.json() as { session_id: string }
  return payload.session_id
}

function hasStructuredSignals(workspace: Record<string, unknown>, structured: Record<string, unknown>) {
  const keys = new Set([
    ...Object.keys(workspace),
    ...Object.keys(structured),
  ])
  const keyText = Array.from(keys).join(' ').toLowerCase()
  return {
    hasStructured: Object.keys(structured).length > 0,
    hasWorldview: /worldview|world_view|世界观|setting|背景/.test(keyText),
    hasCharacters: /character|角色|人物/.test(keyText),
    hasPlot: /plot|outline|情节|大纲/.test(keyText),
    hasGraph: Boolean(
      (workspace.graph as { nodes?: unknown[] } | undefined)?.nodes?.length
      || (workspace.graph as { edges?: unknown[] } | undefined)?.edges?.length,
    ),
  }
}

test.describe('Agent creative flows (Docker)', () => {
  test.describe.configure({ mode: 'serial' })

  test('1) new project: agent creates sci-fi novel with structured data', async ({ page, request }) => {
    test.setTimeout(AGENT_TIMEOUT_MS + 60000)
    await waitForApiReady(request)
    const token = await loginApi(request)
    const model = await resolveAgentModel(request, token)
    const project = await createProject(request, token, `E2E Sci-Fi Agent ${Date.now()}`)
    await setAgentModel(request, token, project.id, model)

    await openProjectWorkspace(page, token, project.id)

    const prompt = [
      '请为全新项目创作一篇科幻短篇小说（约1500字），并自行规划结构化记忆。',
      '你必须输出并存储：世界观、主要角色、情节大纲、关键地点、时间线，以及 graph 节点/边。',
      '完成后将正文写入项目章节，structured_memory 字段由你自行决定命名，但要可检索。',
    ].join('\n')

    const sessionId = await sendAgentMessage(page, prompt, model)
    expect(sessionId).toBeTruthy()
    const session = await waitForAgentSession(request, token, project.id, sessionId)
    expect(['completed', 'partial']).toContain(String(session.status))

    const projectRes = await request.get(`${API_BASE}/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(projectRes.ok()).toBeTruthy()
    const projectData = await projectRes.json() as {
      creative_state?: { agent_workspace?: Record<string, unknown> }
      chapters?: Array<{ content?: string }>
    }
    const workspace = projectData.creative_state?.agent_workspace || {}
    const structured = (workspace.structured_memory || session.plan?.structured_memory || {}) as Record<string, unknown>
    const signals = hasStructuredSignals(workspace, structured)

    expect(signals.hasStructured || signals.hasGraph).toBeTruthy()

    const chapterChars = (projectData.chapters || [])
      .reduce((sum, ch) => sum + String(ch.content || '').length, 0)
    const agentOutput = (session.messages || [])
      .filter((m) => m.role === 'assistant' || m.role === 'agent')
      .map((m) => String(m.content || ''))
      .join('\n')
    expect(chapterChars + agentOutput.length).toBeGreaterThan(300)

    await page.getByRole('button', { name: 'Graph', exact: true }).click()
    await expect(page.getByText(/Structured Data|Elements|Content|Memory/i).first()).toBeVisible({ timeout: 15000 })
  })

  test('2) import existing novel: analyze and continue one chapter', async ({ page, request }) => {
    test.setTimeout(AGENT_TIMEOUT_MS * 2 + 180000)
    await waitForApiReady(request)
    const token = await loginApi(request)
    const model = await resolveAgentModel(request, token)
    const project = await createProject(request, token, `E2E Import Novel ${Date.now()}`)
    await setAgentModel(request, token, project.id, model)

    await importNovelChapter(request, token, project.id, '星港余烬 节选', SAMPLE_NOVEL)
    await openProjectWorkspace(page, token, project.id)
    // Brief pause before first agent call to reduce back-to-back LLM pressure.
    await new Promise((r) => setTimeout(r, 5000))
    await waitForApiReady(request)

    const analyzePrompt = [
      '请分析项目中已导入的章节《星港余烬 节选》，自行决定需要提取的结构化元素（世界观、角色、地点、时间线、冲突、伏笔等），',
      '写入 structured_memory 与 graph，并给出续写建议。',
      '优先读取章节内容，不要重复粘贴原文。',
    ].join('\n')

    const analyzeSessionId = await sendAgentMessage(page, analyzePrompt, model)
    expect(analyzeSessionId).toBeTruthy()

    const analyzeSession = await waitForAgentSession(
      request, token, project.id, analyzeSessionId, AGENT_TIMEOUT_MS,
    )
    expect(['completed', 'partial']).toContain(String(analyzeSession.status))

    const continuePrompt = [
      '基于你刚才的分析结果与 structured_memory，续写下一章（约800字）。',
      '保持角色口吻一致，引用已提取的时间线与地点设定，并将续写内容写入章节。',
    ].join('\n')

    const continueSessionId = await startAgentChatApi(
      request, token, project.id, continuePrompt, model,
    )
    expect(continueSessionId).toBeTruthy()

    const continueSession = await waitForAgentSession(
      request, token, project.id, continueSessionId, AGENT_TIMEOUT_MS,
    )
    expect(['completed', 'partial']).toContain(String(continueSession.status))

    await page.reload()
    await page.waitForLoadState('domcontentloaded')
    await expect(page.getByTestId('agent-chat-input')).toBeVisible({ timeout: 30000 })

    const projectRes = await request.get(`${API_BASE}/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const projectData = await projectRes.json() as {
      creative_state?: { agent_workspace?: Record<string, unknown> }
      chapters?: Array<{ title?: string; content?: string }>
    }
    const workspace = projectData.creative_state?.agent_workspace || {}
    const structured = (workspace.structured_memory || {}) as Record<string, unknown>
    const signals = hasStructuredSignals(workspace, structured)
    expect(signals.hasStructured || signals.hasGraph).toBeTruthy()

    const allText = [
      ...(projectData.chapters || []).map((c) => String(c.content || '')),
      ...(continueSession.messages || []).map((m) => String(m.content || '')),
    ].join('\n')
    expect(allText.length).toBeGreaterThan(500)

    await page.getByRole('button', { name: 'Editor', exact: true }).first().click()
    await page.getByRole('button', { name: 'Graph', exact: true }).first().click()
    await expect(page.getByText(/Structured Data|Elements|worldview|角色|characters|timeline/i).first()).toBeVisible({ timeout: 20000 })
  })
})
