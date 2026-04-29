import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AdminTasksTab from '@/components/admin/AdminTasksTab.vue'
import type { AdminTask } from '@/types'

type TaskStatusFilter = '' | 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'

const CardStub = defineComponent({
  name: 'Card',
  template: '<div><slot /></div>',
})

const AlertStub = defineComponent({
  name: 'Alert',
  template: '<div><slot /></div>',
})

const InputStub = defineComponent({
  name: 'Input',
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
  },
  emits: ['update:modelValue'],
  template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
})

const SelectStub = defineComponent({
  name: 'Select',
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
  },
  emits: ['update:modelValue'],
  template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
})

const ButtonStub = defineComponent({
  name: 'Button',
  props: {
    disabled: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
})

function makeTask(overrides: Partial<AdminTask>): AdminTask {
  return {
    task_id: 'task-1',
    task_type: 'graph_build',
    status: 'pending',
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
    progress: 10,
    message: 'task message',
    result: null,
    error: null,
    metadata: {
      project_id: 'project-1',
      user_id: 'user-1',
    },
    ...overrides,
  }
}

function baseProps() {
  return {
    tasks: [] as AdminTask[],
    total: 0,
    loading: false,
    error: '',
    message: '',
    filters: {
      status: '' as TaskStatusFilter,
      task_type: '',
      project_id: '',
      user_id: '',
      limit: 200,
    },
    cancellingTaskIds: [] as string[],
    formatDateTime: () => 'date',
  }
}

describe('AdminTasksTab', () => {
  it('emits updated filters when status changes', async () => {
    const wrapper = mount(AdminTasksTab, {
      props: baseProps(),
      global: {
        stubs: {
          Card: CardStub,
          Alert: AlertStub,
          Input: InputStub,
          Select: SelectStub,
          Button: ButtonStub,
        },
      },
    })

    const select = wrapper.findComponent(SelectStub)
    select.vm.$emit('update:modelValue', 'processing')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:filters')?.[0]).toEqual([
      {
        status: 'processing',
        task_type: '',
        project_id: '',
        user_id: '',
        limit: 200,
      },
    ])
  })

  it('emits refresh when refresh button is clicked', async () => {
    const wrapper = mount(AdminTasksTab, {
      props: baseProps(),
      global: {
        stubs: {
          Card: CardStub,
          Alert: AlertStub,
          Input: InputStub,
          Select: SelectStub,
          Button: ButtonStub,
        },
      },
    })

    const refreshButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Refresh'))

    expect(refreshButton).toBeTruthy()
    await refreshButton!.trigger('click')

    expect(wrapper.emitted('refresh')).toBeTruthy()
  })

  it('shows cancel only for pending/processing and emits cancel payload', async () => {
    const pending = makeTask({ task_id: 'pending-1', status: 'pending' })
    const processing = makeTask({ task_id: 'processing-1', status: 'processing' })
    const done = makeTask({ task_id: 'done-1', status: 'completed' })

    const wrapper = mount(AdminTasksTab, {
      props: {
        ...baseProps(),
        tasks: [pending, processing, done],
      },
      global: {
        stubs: {
          Card: CardStub,
          Alert: AlertStub,
          Input: InputStub,
          Select: SelectStub,
          Button: ButtonStub,
        },
      },
    })

    const cancelButtons = wrapper
      .findAll('button')
      .filter((button) => button.text().trim() === 'Cancel')

    expect(cancelButtons).toHaveLength(2)

    await cancelButtons[0].trigger('click')
    expect(wrapper.emitted('cancel')?.[0]).toEqual([pending])
  })
})
