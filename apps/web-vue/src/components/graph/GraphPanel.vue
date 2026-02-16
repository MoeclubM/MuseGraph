<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as d3 from 'd3'
import type { GraphData, GraphNode, GraphEdge } from '@/types'

const props = defineProps<{
  data: GraphData
}>()

const emit = defineEmits<{
  'node-click': [node: GraphNode]
}>()

const container = ref<HTMLDivElement | null>(null)
const selectedNode = ref<GraphNode | null>(null)

const NODE_COLORS: Record<string, string> = {
  PERSON: '#3b82f6',
  PLACE: '#10b981',
  ORGANIZATION: '#f59e0b',
  CONCEPT: '#8b5cf6',
  EVENT: '#ef4444',
  OBJECT: '#06b6d4',
  DATE: '#ec4899',
  DEFAULT: '#64748b',
}

function getNodeColor(type: string): string {
  return NODE_COLORS[type?.toUpperCase()] || NODE_COLORS.DEFAULT
}

const KNOWN_NODE_KEYS = new Set(['id', 'label', 'type', 'x', 'y', 'fx', 'fy', 'vx', 'vy', 'index'])

function extraProps(node: GraphNode): [string, any][] {
  return Object.entries(node).filter(([key]) => !KNOWN_NODE_KEYS.has(key))
}

let simulation: d3.Simulation<any, any> | null = null

function renderGraph() {
  if (!container.value || !props.data) return

  const el = container.value
  d3.select(el).selectAll('*').remove()

  const width = el.clientWidth
  const height = el.clientHeight

  if (props.data.nodes.length === 0) return

  const svg = d3
    .select(el)
    .append('svg')
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', [0, 0, width, height])

  // Arrow marker
  svg
    .append('defs')
    .append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 20)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#475569')

  const g = svg.append('g')

  // Zoom
  const zoom = d3
    .zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.1, 4])
    .on('zoom', (event) => {
      g.attr('transform', event.transform)
    })

  svg.call(zoom)

  // Build node/link data
  const nodeMap = new Map<string, any>()
  props.data.nodes.forEach((n) => {
    nodeMap.set(n.id, { ...n, x: width / 2 + Math.random() * 100 - 50, y: height / 2 + Math.random() * 100 - 50 })
  })

  const nodes = Array.from(nodeMap.values())
  const links = props.data.edges
    .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
    .map((e) => ({
      ...e,
      source: e.source,
      target: e.target,
    }))

  // Simulation
  simulation = d3
    .forceSimulation(nodes)
    .force(
      'link',
      d3
        .forceLink(links)
        .id((d: any) => d.id)
        .distance(120)
    )
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(40))

  // Links
  const link = g
    .append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', '#475569')
    .attr('stroke-width', 1.5)
    .attr('marker-end', 'url(#arrowhead)')

  // Link labels
  const linkLabel = g
    .append('g')
    .selectAll('text')
    .data(links)
    .join('text')
    .text((d: any) => d.label || '')
    .attr('font-size', '9px')
    .attr('fill', '#64748b')
    .attr('text-anchor', 'middle')
    .attr('dy', -4)

  // Nodes
  const node = g
    .append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .style('cursor', 'pointer')
    .call(
      d3
        .drag<any, any>()
        .on('start', (event, d) => {
          if (!event.active) simulation!.alphaTarget(0.3).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on('end', (event, d) => {
          if (!event.active) simulation!.alphaTarget(0)
          d.fx = null
          d.fy = null
        })
    )

  node
    .append('circle')
    .attr('r', 12)
    .attr('fill', (d: any) => getNodeColor(d.type))
    .attr('stroke', (d: any) => d3.color(getNodeColor(d.type))!.brighter(0.5).toString())
    .attr('stroke-width', 2)

  node
    .append('text')
    .text((d: any) => d.label || d.id)
    .attr('font-size', '11px')
    .attr('fill', '#e2e8f0')
    .attr('text-anchor', 'middle')
    .attr('dy', -18)

  node.on('click', (_event: any, d: any) => {
    selectedNode.value = d
    emit('node-click', d)
  })

  simulation.on('tick', () => {
    link
      .attr('x1', (d: any) => d.source.x)
      .attr('y1', (d: any) => d.source.y)
      .attr('x2', (d: any) => d.target.x)
      .attr('y2', (d: any) => d.target.y)

    linkLabel
      .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
      .attr('y', (d: any) => (d.source.y + d.target.y) / 2)

    node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
  })
}

watch(
  () => props.data,
  () => nextTick(renderGraph),
  { deep: true }
)

onMounted(() => {
  nextTick(renderGraph)
  window.addEventListener('resize', renderGraph)
})

onUnmounted(() => {
  if (simulation) simulation.stop()
  window.removeEventListener('resize', renderGraph)
})
</script>

<template>
  <div class="relative w-full h-full min-h-[200px]">
    <div ref="container" class="w-full h-full bg-slate-900 rounded-lg border border-slate-700/50 overflow-hidden" />

    <!-- Legend -->
    <div class="absolute top-3 left-3 bg-slate-800/90 backdrop-blur-sm rounded-lg border border-slate-700/50 p-3">
      <p class="text-xs font-medium text-slate-400 mb-2">Entity Types</p>
      <div class="space-y-1">
        <div
          v-for="(color, type) in NODE_COLORS"
          :key="type"
          class="flex items-center gap-2"
        >
          <span class="w-3 h-3 rounded-full" :style="{ backgroundColor: color }" />
          <span class="text-xs text-slate-400">{{ type }}</span>
        </div>
      </div>
    </div>

    <!-- Selected node info -->
    <Transition
      enter-active-class="transition-all duration-200"
      leave-active-class="transition-all duration-200"
      enter-from-class="opacity-0 translate-y-2"
      leave-to-class="opacity-0 translate-y-2"
    >
      <div
        v-if="selectedNode"
        class="absolute bottom-3 left-3 right-3 bg-slate-800/90 backdrop-blur-sm rounded-lg border border-slate-700/50 p-4"
      >
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <span
              class="w-3 h-3 rounded-full"
              :style="{ backgroundColor: getNodeColor(selectedNode.type) }"
            />
            <span class="text-sm font-medium text-slate-200">{{ selectedNode.label }}</span>
            <span class="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-400">
              {{ selectedNode.type }}
            </span>
          </div>
          <button
            class="text-slate-500 hover:text-slate-300 transition-colors"
            @click="selectedNode = null"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div v-if="extraProps(selectedNode).length > 0" class="space-y-1">
          <div
            v-for="[key, value] in extraProps(selectedNode)"
            :key="key"
            class="flex gap-2 text-xs"
          >
            <span class="text-slate-500">{{ key }}:</span>
            <span class="text-slate-300">{{ value }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
