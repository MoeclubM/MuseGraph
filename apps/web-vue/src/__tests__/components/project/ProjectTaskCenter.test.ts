import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ProjectTaskCenter from '@/components/project/ProjectTaskCenter.vue'
import type { OasisTask } from '@/types'

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

const AlertStub = defineComponent({
  name: 'Alert',
  template: '<div><slot /></div>',
})

function buildTask(overrides: Partial<OasisTask>): OasisTask {
  return {
    task_id: 'task-1',
    task_type: 'graph_build',
    status: 'pending',
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
    progress: 0,
    message: 'task-message',
    result: null,
    error: null,
    metadata: null,
    ...overrides,
  }
}

describe('ProjectTaskCenter', () => {
  it('shows running count and emits cancel for cancellable task', async () => {
    const pendingTask = buildTask({ task_id: 'pending-1', status: 'processing', message: 'running task' })
    const doneTask = buildTask({ task_id: 'done-1', status: 'completed', message: 'done task' })

    const wrapper = mount(ProjectTaskCenter, {
      props: {
        tasks: [pendingTask, doneTask],
        loading: false,
        error: null,
        expanded: true,
        filter: 'all',
        cancellingTaskIds: [],
        formatDate: () => 'date',
      },
      global: {
        stubs: {
          teleport: true,
          Button: ButtonStub,
          Select: SelectStub,
          Alert: AlertStub,
        },
      },
    })

    expect(wrapper.text()).toContain('Running 1 / Total 2')
    expect(wrapper.text()).toContain('running task')
    expect(wrapper.text()).toContain('done task')

    const terminateButtons = wrapper
      .findAll('button')
      .filter((button) => button.text().includes('Cancel'))
    expect(terminateButtons).toHaveLength(1)

    await terminateButtons[0].trigger('click')
    expect(wrapper.emitted('cancel')?.[0]).toEqual([pendingTask])
  })

  it('emits normalized filter updates and only shows filtered tasks', async () => {
    const pendingTask = buildTask({ task_id: 'pending-1', status: 'pending', message: 'pending task' })
    const failedTask = buildTask({ task_id: 'failed-1', status: 'failed', message: 'failed task' })

    const wrapper = mount(ProjectTaskCenter, {
      props: {
        tasks: [pendingTask, failedTask],
        loading: false,
        error: null,
        expanded: true,
        filter: 'failed',
        cancellingTaskIds: [],
        formatDate: () => 'date',
      },
      global: {
        stubs: {
          teleport: true,
          Button: ButtonStub,
          Select: SelectStub,
          Alert: AlertStub,
        },
      },
    })

    expect(wrapper.text()).not.toContain('pending task')
    expect(wrapper.text()).toContain('failed task')

    const select = wrapper.findComponent(SelectStub)
    select.vm.$emit('update:modelValue', 'unexpected')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:filter')?.[0]).toEqual(['all'])
  })

  it('emits expanded toggle event from floating action button', async () => {
    const wrapper = mount(ProjectTaskCenter, {
      props: {
        tasks: [],
        loading: false,
        error: null,
        expanded: false,
        filter: 'all',
        cancellingTaskIds: [],
        formatDate: () => 'date',
      },
      global: {
        stubs: {
          teleport: true,
          Button: ButtonStub,
          Select: SelectStub,
          Alert: AlertStub,
        },
      },
    })

    const toggleButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Task Center'))

    expect(toggleButton).toBeTruthy()
    await toggleButton!.trigger('click')

    expect(wrapper.emitted('update:expanded')?.[0]).toEqual([true])
  })

  it('renders the full task id without truncation-only styling', () => {
    const task = buildTask({ task_id: '2b06d808-3a01-495a-aa4a-fb13dfbf9abc', status: 'processing' })

    const wrapper = mount(ProjectTaskCenter, {
      props: {
        tasks: [task],
        loading: false,
        error: null,
        expanded: true,
        filter: 'all',
        cancellingTaskIds: [],
        formatDate: () => 'date',
      },
      global: {
        stubs: {
          teleport: true,
          Button: ButtonStub,
          Select: SelectStub,
          Alert: AlertStub,
        },
      },
    })

    const taskIdNode = wrapper.find('[title="2b06d808-3a01-495a-aa4a-fb13dfbf9abc"]')
    expect(taskIdNode.exists()).toBe(true)
    expect(taskIdNode.text()).toContain('#2b06d808-3a01-495a-aa4a-fb13dfbf9abc')
    expect(taskIdNode.classes()).not.toContain('truncate')
  })
})
