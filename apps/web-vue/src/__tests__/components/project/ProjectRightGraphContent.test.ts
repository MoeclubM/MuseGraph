import { describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import ProjectRightGraphContent from '@/components/project/ProjectRightGraphContent.vue'
import type { GraphData } from '@/types'

const ProjectGraphBuildPanelStub = defineComponent({
  name: 'ProjectGraphBuildPanel',
  emits: [
    'update:ontology-requirement',
    'update:ontology-model',
    'update:graph-build-model',
    'update:graph-embedding-model',
    'update:graph-reranker-model',
    'update:graph-build-mode',
    'generate-ontology',
    'build-graph',
    'resume-graph-build',
  ],
  template: '<div data-test="graph-build-stub" />',
})

const ProjectOasisAnalysisCardStub = defineComponent({
  name: 'ProjectOasisAnalysisCard',
  emits: [
    'update:graph-analysis-prompt',
    'update:oasis-analysis-model',
    'update:oasis-simulation-model',
    'update:oasis-report-model',
    'analyze',
    'prepare',
    'run',
    'report',
    'refresh-status',
  ],
  template: '<div data-test="oasis-stub" />',
})

const GraphPanelStub = defineComponent({
  name: 'GraphPanel',
  template: '<div data-test="graph-panel-stub" />',
})

const GraphSearchStub = defineComponent({
  name: 'GraphSearch',
  props: {
    projectId: {
      type: String,
      required: true,
    },
  },
  template: '<div data-test="graph-search-stub" />',
})

function buildBaseProps() {
  const graphData: GraphData = {
    nodes: [],
    edges: [],
  }
  return {
    rightPanelTab: 'graph',
    workflowSourceTextLength: 0,
    ontologyRequirement: '',
    modelsLoading: false,
    models: [],
    ontologyModel: '',
    ontologyLoading: false,
    graphCanBuild: true,
    ontologyMessage: '',
    ontologyProgress: 0,
    graphParsingFile: null,
    ontologyError: null,
    ontologyData: null,
    hasOntology: false,
    ontologyMeta: null,
    graphBuildModel: '',
    embeddingModels: [],
    rerankerModels: [],
    graphEmbeddingModel: '',
    graphRerankerModel: '',
    graphBuildMode: 'rebuild' as const,
    graphFreshnessState: 'empty',
    graphFreshnessLabel: 'Graph not built',
    graphFreshnessHint: '',
    graphLoading: false,
    graphBuildActionLabel: 'Build',
    graphResumeAvailable: false,
    graphResumeActionLabel: 'Continue Failed Graph Build',
    graphBuildMessage: '',
    graphBuildProgress: 0,
    graphBuildSummary: null,
    graphError: null,
    formatGraphBuildSummary: () => '',
    graphFreshnessClass: () => 'text-stone-500',
    pipeline: [],
    graphReady: false,
    hasOasisAnalysis: false,
    oasisTaskPolling: false,
    oasisPrepareLoading: false,
    oasisTask: null,
    oasisTaskLastId: '',
    graphAnalysisLoading: false,
    graphAnalysisError: null,
    oasisPrepareError: null,
    oasisTaskError: null,
    graphAnalysisResult: null,
    oasisPackage: null,
    oasisRunResult: null,
    oasisReport: null,
    graphAnalysisPrompt: '',
    oasisAnalysisModel: '',
    oasisSimulationModel: '',
    oasisReportModel: '',
    oasisStageClass: () => 'done',
    oasisTaskStatusColor: () => 'ok',
    graphData,
    projectId: 'project-1',
  }
}

describe('ProjectRightGraphContent', () => {
  it('forwards child panel events', async () => {
    const wrapper = mount(ProjectRightGraphContent, {
      props: buildBaseProps() as any,
      global: {
        stubs: {
          ProjectGraphBuildPanel: ProjectGraphBuildPanelStub,
          ProjectOasisAnalysisCard: ProjectOasisAnalysisCardStub,
          GraphPanel: GraphPanelStub,
          GraphSearch: GraphSearchStub,
        },
      },
    })

    const graphBuildStub = wrapper.findComponent(ProjectGraphBuildPanelStub)
    const oasisStub = wrapper.findComponent(ProjectOasisAnalysisCardStub)

    graphBuildStub.vm.$emit('update:graph-build-mode', 'incremental')
    graphBuildStub.vm.$emit('build-graph')
    oasisStub.vm.$emit('update:oasis-report-model', 'report-model-1')
    oasisStub.vm.$emit('analyze')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:graphBuildMode')?.[0]).toEqual(['incremental'])
    expect(wrapper.emitted('build-graph')).toBeTruthy()
    expect(wrapper.emitted('update:oasisReportModel')?.[0]).toEqual(['report-model-1'])
    expect(wrapper.emitted('analyze')).toBeTruthy()
  })

  it('renders graph preview and emits open-full-graph when graph exists', async () => {
    const props = buildBaseProps()
    props.graphData = {
      nodes: [{ id: 'n1', label: 'Node 1', type: 'entity', properties: {} }],
      edges: [],
    }

    const wrapper = mount(ProjectRightGraphContent, {
      props: props as any,
      global: {
        stubs: {
          ProjectGraphBuildPanel: ProjectGraphBuildPanelStub,
          ProjectOasisAnalysisCard: ProjectOasisAnalysisCardStub,
          GraphPanel: GraphPanelStub,
          GraphSearch: GraphSearchStub,
        },
      },
    })

    expect(wrapper.find('[data-test="graph-panel-stub"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Open Full Graph View')

    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('open-full-graph')).toBeTruthy()
  })

  it('shows empty state when graph tab has no nodes', () => {
    const wrapper = mount(ProjectRightGraphContent, {
      props: buildBaseProps() as any,
      global: {
        stubs: {
          ProjectGraphBuildPanel: ProjectGraphBuildPanelStub,
          ProjectOasisAnalysisCard: ProjectOasisAnalysisCardStub,
          GraphPanel: GraphPanelStub,
          GraphSearch: GraphSearchStub,
        },
      },
    })

    expect(wrapper.text()).toContain('Build the graph to preview it here.')
    expect(wrapper.find('[data-test="graph-search-stub"]').exists()).toBe(true)
  })
})
