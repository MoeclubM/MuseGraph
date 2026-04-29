import { describe, expect, it } from 'vitest'
import { defineComponent, markRaw } from 'vue'
import { mount } from '@vue/test-utils'
import ProjectAIOperationsShell from '@/components/project/ProjectAIOperationsShell.vue'

const IconStub = defineComponent({
  name: 'IconStub',
  template: '<span />',
})

const TabsStub = defineComponent({
  name: 'Tabs',
  props: {
    modelValue: {
      type: String,
      default: '',
    },
  },
  emits: ['update:modelValue'],
  template: '<div><slot /></div>',
})

const TabsListStub = defineComponent({
  name: 'TabsList',
  template: '<div><slot /></div>',
})

const TabsTriggerStub = defineComponent({
  name: 'TabsTrigger',
  props: {
    value: {
      type: String,
      default: '',
    },
  },
  template: '<button type="button"><slot /></button>',
})

const AlertStub = defineComponent({
  name: 'Alert',
  template: '<div data-test="alert"><slot /></div>',
})

const ButtonStub = defineComponent({
  name: 'Button',
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
})

function buildBaseProps() {
  return {
    rightPanelCollapsed: false,
    isMobileLayout: false,
    rightPanelTab: 'ai' as const,
    rightPanelTabs: [
      { key: 'graph' as const, label: 'Graph + RAG', icon: markRaw(IconStub) },
      { key: 'ai' as const, label: 'AI Create', icon: markRaw(IconStub) },
      { key: 'oasis' as const, label: 'Scenario Sim', icon: markRaw(IconStub) },
    ],
    graphReady: true,
  }
}

describe('ProjectAIOperationsShell', () => {
  it('shows oasis warning with graph shortcut when graph is missing', async () => {
    const wrapper = mount(ProjectAIOperationsShell, {
      props: {
        ...buildBaseProps(),
        rightPanelTab: 'oasis',
        graphReady: false,
      },
      slots: {
        'ai-content': '<div data-test="ai-slot" />',
        'graph-content': '<div data-test="graph-slot" />',
      },
      global: {
        stubs: {
          Tabs: TabsStub,
          TabsList: TabsListStub,
          TabsTrigger: TabsTriggerStub,
          Alert: AlertStub,
          Button: ButtonStub,
        },
      },
    })

    expect(wrapper.text()).toContain('Graph + RAG · AI Create · Scenario Sim')
    expect(wrapper.get('[data-test="alert"]').text()).toContain('OASIS needs graph context first.')

    await wrapper.get('[data-test="alert"] button').trigger('click')
    expect(wrapper.emitted('update:rightPanelTab')?.[0]).toEqual(['graph'])
  })

  it('does not show duplicate graph warning in ai tab', () => {
    const wrapper = mount(ProjectAIOperationsShell, {
      props: {
        ...buildBaseProps(),
        rightPanelTab: 'ai',
        graphReady: false,
      },
      slots: {
        'ai-content': '<div data-test="ai-slot" />',
        'graph-content': '<div data-test="graph-slot" />',
      },
      global: {
        stubs: {
          Tabs: TabsStub,
          TabsList: TabsListStub,
          TabsTrigger: TabsTriggerStub,
          Alert: AlertStub,
          Button: ButtonStub,
        },
      },
    })

    expect(wrapper.find('[data-test="alert"]').exists()).toBe(false)
  })
})
