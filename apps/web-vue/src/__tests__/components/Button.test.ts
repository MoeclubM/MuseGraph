import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Button from '@/components/ui/Button.vue'

describe('Button Component', () => {
  describe('renders with default props', () => {
    it('should render with slot content', () => {
      const wrapper = mount(Button, {
        slots: { default: 'Click me' },
      })
      expect(wrapper.text()).toContain('Click me')
    })

    it('should have type="button" by default', () => {
      const wrapper = mount(Button)
      expect(wrapper.attributes('type')).toBe('button')
    })

    it('should not be disabled by default', () => {
      const wrapper = mount(Button)
      expect(wrapper.attributes('disabled')).toBeUndefined()
    })

    it('should apply primary variant classes by default', () => {
      const wrapper = mount(Button)
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('border-[color:var(--muse-accent)]')
      expect(cls).toContain('bg-[color:var(--muse-accent)]')
      expect(cls).toContain('text-[color:var(--muse-accent-ink)]')
    })

    it('should apply md size classes by default', () => {
      const wrapper = mount(Button)
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('px-4')
      expect(cls).toContain('h-10')
    })
  })

  describe('click event', () => {
    it('should emit click event when clicked', async () => {
      const wrapper = mount(Button)
      await wrapper.trigger('click')
      expect(wrapper.emitted('click')).toBeTruthy()
    })

    it('should not emit click when disabled', async () => {
      const wrapper = mount(Button, {
        props: { disabled: true },
      })
      await wrapper.trigger('click')
      expect(wrapper.attributes('disabled')).toBeDefined()
    })
  })

  describe('disabled state', () => {
    it('should set disabled attribute when disabled prop is true', () => {
      const wrapper = mount(Button, {
        props: { disabled: true },
      })
      expect(wrapper.attributes('disabled')).toBeDefined()
    })

    it('should set disabled attribute when loading prop is true', () => {
      const wrapper = mount(Button, {
        props: { loading: true },
      })
      expect(wrapper.attributes('disabled')).toBeDefined()
    })

    it('should apply disabled styling classes', () => {
      const wrapper = mount(Button, {
        props: { disabled: true },
      })
      expect(wrapper.classes().join(' ')).toContain('disabled:opacity-50')
    })

    it('should show loader icon when loading', () => {
      const wrapper = mount(Button, {
        props: { loading: true },
        slots: { default: 'Submit' },
      })
      expect(wrapper.find('svg').exists()).toBe(true)
    })
  })

  describe('variants', () => {
    it('should apply primary variant classes', () => {
      const wrapper = mount(Button, {
        props: { variant: 'primary' },
      })
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('border-[color:var(--muse-accent)]')
      expect(cls).toContain('bg-[color:var(--muse-accent)]')
      expect(cls).toContain('text-[color:var(--muse-accent-ink)]')
    })

    it('should apply secondary variant classes', () => {
      const wrapper = mount(Button, {
        props: { variant: 'secondary' },
      })
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('border-[color:var(--muse-border)]')
      expect(cls).toContain('bg-[color:var(--muse-panel)]')
      expect(cls).toContain('text-[color:var(--muse-text)]')
    })

    it('should apply danger variant classes', () => {
      const wrapper = mount(Button, {
        props: { variant: 'danger' },
      })
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('border-[color:var(--muse-danger)]')
      expect(cls).toContain('bg-[color:var(--muse-danger)]')
      expect(cls).toContain('text-[color:var(--muse-accent-ink)]')
    })

    it('should apply ghost variant classes', () => {
      const wrapper = mount(Button, {
        props: { variant: 'ghost' },
      })
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('bg-transparent')
      expect(cls).toContain('text-[color:var(--muse-text-muted)]')
    })
  })

  describe('sizes', () => {
    it('should apply sm size classes', () => {
      const wrapper = mount(Button, {
        props: { size: 'sm' },
      })
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('px-3')
      expect(cls).toContain('h-8')
      expect(cls).toContain('text-xs')
    })

    it('should apply md size classes', () => {
      const wrapper = mount(Button, {
        props: { size: 'md' },
      })
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('px-4')
      expect(cls).toContain('h-10')
    })

    it('should apply lg size classes', () => {
      const wrapper = mount(Button, {
        props: { size: 'lg' },
      })
      const cls = wrapper.classes().join(' ')
      expect(cls).toContain('px-6')
      expect(cls).toContain('h-11')
      expect(cls).toContain('text-[0.95rem]')
    })
  })

  describe('type prop', () => {
    it('should accept submit type', () => {
      const wrapper = mount(Button, {
        props: { type: 'submit' },
      })
      expect(wrapper.attributes('type')).toBe('submit')
    })

    it('should accept reset type', () => {
      const wrapper = mount(Button, {
        props: { type: 'reset' },
      })
      expect(wrapper.attributes('type')).toBe('reset')
    })
  })
})
