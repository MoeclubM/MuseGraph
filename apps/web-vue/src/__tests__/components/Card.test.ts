import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Card from '@/components/ui/Card.vue'

describe('Card', () => {
  it('renders default variant with standard padding', () => {
    const wrapper = mount(Card, { slots: { default: 'Body' } })
    expect(wrapper.classes()).toContain('muse-card')
    expect(wrapper.classes()).toContain('p-5')
  })

  it('renders stat variant without duplicate padding utilities', () => {
    const wrapper = mount(Card, {
      props: { variant: 'stat' },
      slots: { default: 'Stat' },
    })
    expect(wrapper.classes()).toContain('muse-card-stat')
    expect(wrapper.classes()).not.toContain('p-5')
  })

  it('renders interactive tile variant for clickable cards', () => {
    const wrapper = mount(Card, {
      props: { variant: 'interactive' },
      slots: { default: 'Tile' },
    })
    expect(wrapper.classes()).toContain('muse-card-interactive-tile')
  })
})
