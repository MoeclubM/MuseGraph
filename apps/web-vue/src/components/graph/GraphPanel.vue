<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as d3 from 'd3'
import type { GraphData, GraphEdge, GraphNode } from '@/types'

const props = defineProps<{
  data: GraphData
}>()

const emit = defineEmits<{
  'node-click': [node: GraphNode]
}>()

const container = ref<HTMLDivElement | null>(null)
const selectedNode = ref<GraphNode | null>(null)
const searchQuery = ref('')
const selectedTypes = ref<Set<string>>(new Set())
const markerId = `arrowhead-${Math.random().toString(36).slice(2)}`
let currentZoomTransform = d3.zoomIdentity

const NODE_COLORS: Record<string, string> = {
  Entity: '#a16207',
  EntityType: '#0f766e',
  TextSummary: '#be185d',
  DocumentChunk: '#6d28d9',
  TextDocument: '#78716c',
  Person: '#2563eb',
  Place: '#0f766e',
  Location: '#0f766e',
  Organization: '#c2410c',
  Faction: '#b45309',
  Family: '#a21caf',
  Role: '#0284c7',
  Concept: '#7c3aed',
  Event: '#dc2626',
  Object: '#0891b2',
  Book: '#92400e',
  Ability: '#16a34a',
  SupernaturalBeing: '#9333ea',
  TimePoint: '#db2777',
  Date: '#db2777',
  DEFAULT: '#78716c',
}

const EDGE_COLORS = ['#64748b', '#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#be185d']
const KNOWN_NODE_KEYS = new Set(['id', 'label', 'type', 'x', 'y', 'fx', 'fy', 'vx', 'vy', 'index', 'degree'])

let simulation: d3.Simulation<any, any> | null = null

function normalizeNodeType(type: string): string {
  const raw = String(type || '').trim()
  if (!raw) return 'Entity'
  const key = raw.replace(/[^a-zA-Z0-9_]/g, '').toLowerCase()
  const aliases: Record<string, string> = {
    entitytype: 'EntityType',
    textsummary: 'TextSummary',
    summary: 'TextSummary',
    documentchunk: 'DocumentChunk',
    chunk: 'DocumentChunk',
    textdocument: 'TextDocument',
    document: 'TextDocument',
    entity: 'Entity',
    person: 'Person',
    people: 'Person',
    place: 'Place',
    location: 'Location',
    organization: 'Organization',
    organisation: 'Organization',
    faction: 'Faction',
    family: 'Family',
    role: 'Role',
    concept: 'Concept',
    event: 'Event',
    object: 'Object',
    item: 'Object',
    book: 'Book',
    ability: 'Ability',
    supernaturalbeing: 'SupernaturalBeing',
    timepoint: 'TimePoint',
    date: 'Date',
  }
  return aliases[key] || raw
}

function getNodeColor(type: string): string {
  const normalized = normalizeNodeType(type)
  return NODE_COLORS[normalized] || NODE_COLORS[normalized.toUpperCase()] || NODE_COLORS.DEFAULT
}

function getEdgeColor(label: string, isDark: boolean): string {
  const text = String(label || 'RELATED_TO')
  let hash = 0
  for (let index = 0; index < text.length; index += 1) hash = (hash * 31 + text.charCodeAt(index)) >>> 0
  const color = EDGE_COLORS[hash % EDGE_COLORS.length]
  return isDark ? d3.color(color)?.brighter(0.35).toString() || color : color
}

function normalizeEndpoint(value: any): string {
  if (value && typeof value === 'object') return String(value.id || '')
  return String(value || '')
}

function nodeSearchText(node: GraphNode): string {
  return [node.id, node.label, node.type, node.summary, JSON.stringify(node.attributes || {})]
    .join(' ')
    .toLowerCase()
}

function matchesSearch(node: GraphNode, query: string): boolean {
  return !query || nodeSearchText(node).includes(query)
}

function formatValue(value: any): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function graphContentSignature(data: GraphData): string {
  const nodes = data?.nodes || []
  const edges = data?.edges || []
  const nodeText = nodes
    .map((node) => [node.id, node.label, normalizeNodeType(node.type), node.summary || '', formatValue(node.attributes || {})].join('\u001f'))
    .join('\u001e')
  const edgeText = edges
    .map((edge) => [
      edge.id || '',
      normalizeEndpoint(edge.source),
      normalizeEndpoint(edge.target),
      edge.label || '',
      edge.type || '',
      edge.fact || '',
    ].join('\u001f'))
    .join('\u001e')
  return `${nodes.length}\u001d${edges.length}\u001d${nodeText}\u001d${edgeText}`
}

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
    .map(([type, count]) => ({ type, count, color: getNodeColor(type) }))
})

const activeTypeKey = computed(() => Array.from(selectedTypes.value).sort().join('|'))

function typeIsActive(type: string): boolean {
  return selectedTypes.value.size === 0 || selectedTypes.value.has(type)
}

function toggleType(type: string) {
  const next = new Set(selectedTypes.value)
  if (next.has(type)) next.delete(type)
  else next.add(type)
  selectedTypes.value = next
}

function resetFilters() {
  selectedTypes.value = new Set()
  searchQuery.value = ''
  selectedNode.value = null
}

function buildFilteredGraph(): GraphData {
  const nodes = props.data?.nodes || []
  const edges = props.data?.edges || []
  const query = searchQuery.value.trim().toLowerCase()
  const typeFilteredIds = new Set<string>()
  const matchingIds = new Set<string>()

  for (const node of nodes) {
    const type = normalizeNodeType(node.type)
    if (!typeIsActive(type)) continue
    typeFilteredIds.add(node.id)
    if (matchesSearch(node, query)) matchingIds.add(node.id)
  }

  const visibleIds = new Set<string>()
  if (query) {
    for (const id of matchingIds) visibleIds.add(id)
    for (const edge of edges) {
      const source = normalizeEndpoint(edge.source)
      const target = normalizeEndpoint(edge.target)
      if (!typeFilteredIds.has(source) || !typeFilteredIds.has(target)) continue
      if (matchingIds.has(source) || matchingIds.has(target)) {
        visibleIds.add(source)
        visibleIds.add(target)
      }
    }
  } else {
    for (const id of typeFilteredIds) visibleIds.add(id)
  }

  return {
    nodes: nodes.filter((node) => visibleIds.has(node.id)),
    edges: edges.filter((edge) => visibleIds.has(normalizeEndpoint(edge.source)) && visibleIds.has(normalizeEndpoint(edge.target))),
  }
}

const filteredGraph = computed(buildFilteredGraph)
const graphContentKey = computed(() => graphContentSignature(props.data))

const selectedRelations = computed(() => {
  const node = selectedNode.value
  if (!node) return []
  const labels = new Map((props.data?.nodes || []).map((item) => [item.id, item.label || item.id]))
  return (props.data?.edges || [])
    .filter((edge) => normalizeEndpoint(edge.source) === node.id || normalizeEndpoint(edge.target) === node.id)
    .slice(0, 16)
    .map((edge) => {
      const source = normalizeEndpoint(edge.source)
      const target = normalizeEndpoint(edge.target)
      const outgoing = source === node.id
      const other = outgoing ? target : source
      return {
        label: edge.label || edge.type || 'RELATED_TO',
        otherLabel: labels.get(other) || other,
        direction: outgoing ? 'to' : 'from',
        fact: edge.fact || '',
      }
    })
})

const visibleSummary = computed(() => ({
  nodes: filteredGraph.value.nodes.length,
  edges: filteredGraph.value.edges.length,
  totalNodes: props.data?.nodes?.length || 0,
  totalEdges: props.data?.edges?.length || 0,
}))

function nodeRadius(node: any): number {
  return 8 + Math.min(12, Math.sqrt(Math.max(0, Number(node.degree || 0))) * 3)
}

function renderGraph() {
  if (!container.value || !props.data) return

  const el = container.value
  if (simulation) {
    simulation.stop()
    simulation = null
  }
  d3.select(el).selectAll('*').remove()

  const width = el.clientWidth
  const height = el.clientHeight
  if (width <= 0 || height <= 0) return
  const isDark = document.documentElement.classList.contains('dark')
  const mutedEdgeColor = isDark ? '#52525b' : '#d6d3d1'
  const labelColor = isDark ? '#a1a1aa' : '#57534e'
  const nodeTextColor = isDark ? '#f4f4f5' : '#292524'
  const graph = filteredGraph.value

  if (graph.nodes.length === 0) return

  const svg = d3
    .select(el)
    .append('svg')
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', [0, 0, width, height])

  svg
    .append('defs')
    .append('marker')
    .attr('id', markerId)
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 22)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', mutedEdgeColor)

  const g = svg.append('g')
  const zoom = d3
    .zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.12, 5])
    .on('zoom', (event) => {
      currentZoomTransform = event.transform
      g.attr('transform', event.transform)
    })
  svg.call(zoom)
  svg.call(zoom.transform, currentZoomTransform)

  const nodeMap = new Map<string, any>()
  const ringRadius = Math.max(80, Math.min(width, height) * 0.28)
  graph.nodes.forEach((node, index) => {
    const angle = (index / Math.max(1, graph.nodes.length)) * Math.PI * 2
    nodeMap.set(node.id, {
      ...node,
      type: normalizeNodeType(node.type),
      degree: 0,
      x: width / 2 + Math.cos(angle) * ringRadius,
      y: height / 2 + Math.sin(angle) * ringRadius,
    })
  })

  const links = graph.edges
    .filter((edge) => nodeMap.has(normalizeEndpoint(edge.source)) && nodeMap.has(normalizeEndpoint(edge.target)))
    .map((edge, index) => {
      const source = normalizeEndpoint(edge.source)
      const target = normalizeEndpoint(edge.target)
      nodeMap.get(source).degree += 1
      nodeMap.get(target).degree += 1
      return { ...edge, id: edge.id || `${source}:${target}:${index}`, source, target }
    })

  const nodes = Array.from(nodeMap.values())
  const query = searchQuery.value.trim().toLowerCase()
  const matchedIds = new Set(nodes.filter((node) => matchesSearch(node, query)).map((node) => node.id))
  const selectedId = selectedNode.value && nodeMap.has(selectedNode.value.id) ? selectedNode.value.id : ''
  const neighborIds = new Set<string>()
  if (selectedId) {
    for (const edge of links) {
      if (edge.source === selectedId) neighborIds.add(edge.target)
      if (edge.target === selectedId) neighborIds.add(edge.source)
    }
  }
  const typeOrder = legendItems.value.map((item) => item.type)
  const typeIndex = new Map(typeOrder.map((type, index) => [type, index]))

  const shouldRenderLabels = nodes.length <= 220 || Boolean(query) || Boolean(selectedId)
  const shouldRenderLinkLabels = links.length <= 180 || Boolean(selectedId)

  simulation = d3
    .forceSimulation(nodes)
    .force('link', d3.forceLink(links).id((node: any) => node.id).distance((edge: any) => 95 + Math.min(70, Math.max(0, 5 - Math.min(nodeMap.get(edge.source.id || edge.source)?.degree || 0, nodeMap.get(edge.target.id || edge.target)?.degree || 0)) * 12)))
    .force('charge', d3.forceManyBody().strength(-260))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('x', d3.forceX((node: any) => {
      const index = typeIndex.get(normalizeNodeType(node.type)) || 0
      const ratio = typeOrder.length <= 1 ? 0.5 : index / (typeOrder.length - 1)
      return width * (0.18 + ratio * 0.64)
    }).strength(0.035))
    .force('y', d3.forceY(height / 2).strength(0.04))
    .force('collision', d3.forceCollide().radius((node: any) => nodeRadius(node) + 12))

  const link = g
    .append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', (edge: any) => getEdgeColor(edge.label || edge.type, isDark))
    .attr('stroke-width', (edge: any) => selectedId && (edge.source === selectedId || edge.target === selectedId) ? 2.6 : 1.4)
    .attr('stroke-opacity', (edge: any) => {
      if (!selectedId) return 0.68
      return edge.source === selectedId || edge.target === selectedId ? 0.95 : 0.12
    })
    .attr('marker-end', `url(#${markerId})`)

  link.append('title').text((edge: any) => `${edge.label || edge.type || 'RELATED_TO'}\n${edge.fact || ''}`.trim())

  const linkLabel = g
    .append('g')
    .selectAll('text')
    .data(shouldRenderLinkLabels ? links : [])
    .join('text')
    .text((edge: any) => edge.label || '')
    .attr('font-size', '9px')
    .attr('font-weight', 600)
    .attr('fill', labelColor)
    .attr('text-anchor', 'middle')
    .attr('dy', -5)
    .attr('opacity', (edge: any) => selectedId && edge.source !== selectedId && edge.target !== selectedId ? 0.25 : 0.88)

  const node = g
    .append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .style('cursor', 'pointer')
    .attr('opacity', (node: any) => {
      if (selectedId) return node.id === selectedId || neighborIds.has(node.id) ? 1 : 0.22
      if (query) return matchedIds.has(node.id) ? 1 : 0.58
      return 1
    })
    .call(
      d3
        .drag<any, any>()
        .on('start', (event, node) => {
          if (!event.active) simulation!.alphaTarget(0.25).restart()
          node.fx = node.x
          node.fy = node.y
        })
        .on('drag', (event, node) => {
          node.fx = event.x
          node.fy = event.y
        })
        .on('end', (event, node) => {
          if (!event.active) simulation!.alphaTarget(0)
          node.fx = null
          node.fy = null
        })
    )

  node
    .append('circle')
    .attr('r', (node: any) => nodeRadius(node))
    .attr('fill', (node: any) => getNodeColor(node.type))
    .attr('stroke', (node: any) => node.id === selectedId ? '#facc15' : d3.color(getNodeColor(node.type))?.brighter(0.55).toString() || '#ffffff')
    .attr('stroke-width', (node: any) => node.id === selectedId ? 4 : matchedIds.has(node.id) && query ? 3 : 2)

  node
    .append('text')
    .text((node: any) => shouldRenderLabels || node.degree >= 4 ? (node.label || node.id) : '')
    .attr('font-size', (node: any) => node.degree >= 6 ? '12px' : '11px')
    .attr('font-weight', (node: any) => node.degree >= 4 || node.id === selectedId ? 700 : 500)
    .attr('fill', nodeTextColor)
    .attr('paint-order', 'stroke')
    .attr('stroke', isDark ? '#18181b' : '#fafaf9')
    .attr('stroke-width', 3)
    .attr('text-anchor', 'middle')
    .attr('dy', (node: any) => -nodeRadius(node) - 8)

  node.append('title').text((node: any) => `${node.label || node.id}\n${node.type}\nDegree: ${node.degree}`)

  node.on('click', (_event: any, node: any) => {
    selectedNode.value = node
    emit('node-click', node)
  })

  simulation.on('tick', () => {
    link
      .attr('x1', (edge: any) => edge.source.x)
      .attr('y1', (edge: any) => edge.source.y)
      .attr('x2', (edge: any) => edge.target.x)
      .attr('y2', (edge: any) => edge.target.y)

    linkLabel
      .attr('x', (edge: any) => (edge.source.x + edge.target.x) / 2)
      .attr('y', (edge: any) => (edge.source.y + edge.target.y) / 2)

    node.attr('transform', (node: any) => `translate(${node.x},${node.y})`)
  })
}

watch(
  () => [graphContentKey.value, searchQuery.value, activeTypeKey.value, selectedNode.value?.id],
  () => {
    if (selectedNode.value && !filteredGraph.value.nodes.some((node) => node.id === selectedNode.value?.id)) {
      selectedNode.value = null
    }
    nextTick(renderGraph)
  }
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
  <div class="flex h-full min-h-[240px] w-full flex-col overflow-hidden rounded-lg border border-stone-300/80 bg-stone-100 dark:border-zinc-700/50 dark:bg-zinc-900">
    <div class="shrink-0 border-b border-stone-300/80 bg-stone-50/95 p-2 shadow-sm dark:border-zinc-700/60 dark:bg-zinc-900/95">
      <div class="flex flex-wrap items-center gap-2">
      <input
        v-model="searchQuery"
        class="min-w-[220px] flex-1 rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-xs text-stone-700 outline-none transition focus:border-amber-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
        placeholder="Search nodes, types, summaries..."
      />
      <span class="whitespace-nowrap text-xs text-stone-500 dark:text-zinc-400">
        {{ visibleSummary.nodes }}/{{ visibleSummary.totalNodes }} nodes · {{ visibleSummary.edges }}/{{ visibleSummary.totalEdges }} edges
      </span>
      <button
        class="rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs text-stone-600 transition hover:bg-stone-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        @click="resetFilters"
      >
        Reset
      </button>
      </div>
    </div>

    <div class="relative min-h-0 flex-1">
      <div ref="container" class="h-full w-full overflow-hidden bg-stone-100 dark:bg-zinc-900" />

    <div class="absolute left-3 top-3 z-10 max-h-[46%] max-w-[260px] overflow-auto rounded-xl border border-stone-300/80 bg-stone-50/95 p-3 shadow-sm backdrop-blur dark:border-zinc-700/60 dark:bg-zinc-900/90">
      <p class="mb-2 text-xs font-medium text-stone-500 dark:text-zinc-400">Node Types</p>
      <div class="space-y-1">
        <button
          v-for="item in legendItems"
          :key="item.type"
          class="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1 text-left transition hover:bg-stone-100 dark:hover:bg-zinc-800"
          :class="typeIsActive(item.type) ? 'opacity-100' : 'opacity-35'"
          @click="toggleType(item.type)"
        >
          <span class="flex min-w-0 items-center gap-2">
            <span class="h-3 w-3 shrink-0 rounded-full" :style="{ backgroundColor: item.color }" />
            <span class="truncate text-xs text-stone-700 dark:text-zinc-300">{{ item.type }}</span>
          </span>
          <span class="text-xs text-stone-500 dark:text-zinc-500">{{ item.count }}</span>
        </button>
      </div>
    </div>

    <div
      v-if="props.data.nodes.length > 0 && filteredGraph.nodes.length === 0"
      class="absolute inset-0 flex items-center justify-center bg-stone-100/70 text-sm text-stone-500 backdrop-blur-sm dark:bg-zinc-900/70 dark:text-zinc-400"
    >
      No graph nodes match the current filters.
    </div>

    <Transition
      enter-active-class="transition-all duration-200"
      leave-active-class="transition-all duration-200"
      enter-from-class="opacity-0 translate-y-2"
      leave-to-class="opacity-0 translate-y-2"
    >
      <div
        v-if="selectedNode"
        class="absolute bottom-3 left-3 right-3 z-20 max-h-[42%] overflow-auto rounded-xl border border-stone-300/80 bg-stone-50/95 p-4 shadow-sm backdrop-blur dark:border-zinc-700/60 dark:bg-zinc-900/90"
      >
        <div class="mb-3 flex items-center justify-between gap-3">
          <div class="flex min-w-0 items-center gap-2">
            <span class="h-3 w-3 shrink-0 rounded-full" :style="{ backgroundColor: getNodeColor(selectedNode.type) }" />
            <span class="truncate text-sm font-semibold text-stone-800 dark:text-zinc-100">{{ selectedNode.label }}</span>
            <span class="rounded bg-stone-200 px-1.5 py-0.5 text-xs text-stone-600 dark:bg-zinc-700 dark:text-zinc-300">
              {{ normalizeNodeType(selectedNode.type) }}
            </span>
          </div>
          <button
            class="text-stone-500 transition hover:text-stone-700 dark:text-zinc-500 dark:hover:text-zinc-300"
            @click="selectedNode = null"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div v-if="selectedRelations.length > 0" class="mb-3 grid gap-1.5 md:grid-cols-2">
          <div
            v-for="(relation, index) in selectedRelations"
            :key="`${relation.label}-${relation.otherLabel}-${index}`"
            class="rounded-lg border border-stone-200 bg-white/70 px-2 py-1.5 text-xs dark:border-zinc-800 dark:bg-zinc-800/70"
          >
            <div class="font-medium text-stone-700 dark:text-zinc-200">
              {{ relation.direction === 'to' ? '→' : '←' }} {{ relation.label }} {{ relation.otherLabel }}
            </div>
            <div v-if="relation.fact" class="mt-1 line-clamp-2 text-stone-500 dark:text-zinc-400">{{ relation.fact }}</div>
          </div>
        </div>

        <div v-if="extraProps(selectedNode).length > 0" class="grid gap-1.5 text-xs md:grid-cols-2">
          <div
            v-for="[key, value] in extraProps(selectedNode)"
            :key="key"
            class="flex gap-2 rounded-lg bg-stone-100/80 px-2 py-1 dark:bg-zinc-800/80"
          >
            <span class="shrink-0 text-stone-500 dark:text-zinc-500">{{ key }}:</span>
            <span class="min-w-0 break-words text-stone-700 dark:text-zinc-300">{{ formatValue(value) }}</span>
          </div>
        </div>
      </div>
    </Transition>
    </div>
  </div>
</template>
