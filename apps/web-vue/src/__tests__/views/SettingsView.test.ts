import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsView from '@/views/SettingsView.vue'
import { createTestI18n } from '@/__tests__/helpers/i18n'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/billing', () => ({
  getBalance: vi.fn().mockResolvedValue({
    balance: 10,
    daily_usage: 1,
    monthly_usage: 2,
  }),
}))

vi.mock('@/api/users', () => ({
  getUserUsage: vi.fn().mockResolvedValue({
    total_tokens: 100,
    total_cost: 3,
    total_requests: 5,
  }),
}))

vi.mock('@/api/usage', () => ({
  getMyUsageDetails: vi.fn().mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 10,
    total_pages: 0,
  }),
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRouter: () => ({ push: vi.fn() }),
  }
})

describe('SettingsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    useAuthStore().user = {
      id: 'user-1',
      email: 'user@example.com',
      nickname: 'Muse',
      avatar: null,
      balance: 10,
      is_admin: false,
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
    }
  })

  it('renders account settings with shared UI components', async () => {
    const i18n = createTestI18n('zh-CN')
    const wrapper = mount(SettingsView, {
      global: {
        plugins: [i18n],
        stubs: {
          AppLayout: { template: '<div><slot /></div>' },
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('个人资料')
    expect(wrapper.text()).toContain('Muse')
    expect(wrapper.findAll('button').length).toBeGreaterThanOrEqual(3)
  })
})
