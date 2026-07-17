import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchInput from '@/components/ui/SearchInput.vue'

describe('SearchInput', () => {
  it('renders with panel search classes and aria-label', () => {
    const wrapper = mount(SearchInput, {
      props: {
        placeholder: '搜索实体…',
        ariaLabel: '搜索实体',
        testId: 'test-search',
      },
    })
    const input = wrapper.find('[data-testid="test-search"]')
    expect(input.exists()).toBe(true)
    expect(input.classes()).toContain('muse-panel-search-input')
    expect(input.attributes('aria-label')).toBe('搜索实体')
    expect(wrapper.find('.muse-panel-search-icon').exists()).toBe(true)
  })

  it('emits search on Enter', async () => {
    const wrapper = mount(SearchInput, {
      props: { modelValue: 'query' },
    })
    await wrapper.find('input').trigger('keydown.enter')
    expect(wrapper.emitted('search')).toHaveLength(1)
  })
})