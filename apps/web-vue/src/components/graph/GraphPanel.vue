<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
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
  Entity: '#a16207',
  EntityType: '#0f766e',
  TextSummary: '#be185d',
  DocumentChunk: '#6d28d9',
  TextDocument: '#78716c',
  PERSON: '#2563eb',
  PLACE: '#0f766e',
  ORGANIZATION: '#c2410c',
  CONCEPT: '#7c3aed',
  EVENT: '#dc2626',
  OBJECT: '#0891b2',
  DATE: '#db2777',
  DEFAULT: '#a8a29e',
}

function normalizeNodeType(type: string): string {
  const raw = String(type || '').trim()
  if (!raw) return 'Entity'
  const key = raw.replace(/[^a-zA-Z0-9_]/g, '').toLowerCase()
  if (key === 'entitytype') return 'EntityType'
  if (key === 'textsummary' || key === 'summary') return 'TextSummary'
  if (key === 'documentchunk' || key === 'chunk') return 'DocumentChunk'
  if (key === 'textdocument' || key === 'document') return 'TextDocument'
  if (key === 'entity') return 'Entity'
  return raw
}

function getNodeColor(type: string): string {
  const normalized = normalizeNodeType(type)
  return NODE_COLORS[normalized] || NODE_COLORS[normalized.toUpperCase()] || NODE_COLORS.DEFAULT
}

const KNOWN_NODE_KEYS = new Set(['id', 'label', 'type', 'x', 'y', 'fx', 'fy', 'vx', 'vy', 'index'])

function extraProps(node: GraphNode): [string, any][] {
  return Object.entries(node).filter(([key]) => !KNOWN_NODE_KEYS.has(key))
}

const legendItems = computed(() => {
  const counts = new Map<string, number>()
  for (const node of props.data?.nodes || []) {
    const type = normalizeNodeType(node.type)
    counts.set(type, (counts.get(type) || 0) + 1)
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => ({
      type,
      count,
      color: getNodeColor(type),
    }))
})

let simulation: d3.Simulation<any, any> | null = null

function renderGraph() {
  if (!container.value || !props.data) return

  const el = container.value
  d3.select(el).selectAll('*').remove()

  const width = el.clientWidth
  const height = el.clientHeight
  const isDark = document.documentElement.classList.contains('dark')
  const edgeColor = isDark ? '#71717a' : '#a8a29e'
  const labelColor = isDark ? '#a1a1aa' : '#57534e'
  const nodeTextColor = isDark ? '#e4e4e7' : '#44403c'

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
    .attr('fill', edgeColor)

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
    .attr('stroke', edgeColor)
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
    .attr('fill', labelColor)
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
    .attr('fill', nodeTextColor)
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
    <div ref="container" class="w-full h-full bg-stone-100 rounded-lg border border-stone-300/80 overflow-hidden dark:bg-zinc-900 dark:border-zinc-700/50" />

    <!-- Legend -->
    <div class="absolute top-3 left-3 bg-stone-50/95 backdrop-blur-sm rounded-lg border border-stone-300/80 p-3 dark:bg-zinc-800/90 dark:border-zinc-700/60">
      <p class="text-xs font-medium text-stone-500 dark:text-zinc-400 mb-2">Node Types</p>
      <div class="space-y-1">
        <div
          v-for="item in legendItems"
          :key="item.type"
          class="flex items-center gap-2"
        >
          <span class="w-3 h-3 rounded-full" :style="{ backgroundColor: item.color }" />
          <span class="text-xs text-stone-600 dark:text-zinc-400">{{ item.type }} ({{ item.count }})</span>
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
        class="absolute bottom-3 left-3 right-3 bg-stone-50/95 backdrop-blur-sm rounded-lg border border-stone-300/80 p-4 dark:bg-zinc-800/90 dark:border-zinc-700/60"
      >
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <span
              class="w-3 h-3 rounded-full"
              :style="{ backgroundColor: getNodeColor(selectedNode.type) }"
            />
            <span class="text-sm font-medium text-stone-700 dark:text-zinc-200">{{ selectedNode.label }}</span>
            <span class="text-xs px-1.5 py-0.5 rounded bg-stone-200 text-stone-600 dark:bg-zinc-700 dark:text-zinc-400">
              {{ selectedNode.type }}
            </span>
          </div>
          <button
            class="text-stone-500 hover:text-stone-700 dark:text-zinc-500 dark:hover:text-zinc-300 transition-colors"
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
            <span class="text-stone-500 dark:text-zinc-500">{{ key }}:</span>
            <span class="text-stone-700 dark:text-zinc-300">{{ value }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
