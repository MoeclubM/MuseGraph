import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Input from '@/components/ui/Input.vue'

describe('Input', () => {
  it('defaults to md height (h-10)', () => {
    const wrapper = mount(Input, { props: { modelValue: '' } })
    expect(wrapper.find('input').classes().join(' ')).toContain('h-10')
  })

  it('applies sm size', () => {
    const wrapper = mount(Input, { props: { modelValue: '', size: 'sm' } })
    expect(wrapper.find('input').classes().join(' ')).toContain('h-8')
  })

  it('keeps muse-focus-ring for accessibility', () => {
    const wrapper = mount(Input, { props: { modelValue: '' } })
    expect(wrapper.find('input').classes().join(' ')).toContain('muse-focus-ring')
  })
})