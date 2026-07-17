<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { useAgentLayoutStore } from '@/stores/agentLayout'
import type { ColumnId } from '@/stores/agentLayout'

const props = defineProps<{
  left: ColumnId
  right: ColumnId
}>()

const emit = defineEmits<{
  resize: [deltaX: number]
}>()

const layoutStore = useAgentLayoutStore()

let dragging = false
let lastX = 0

function onPointerDown(event: PointerEvent) {
  layoutStore.beginColumnResize()
  dragging = true
  lastX = event.clientX
  if (event.currentTarget instanceof HTMLElement) {
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onPointerMove(event: PointerEvent) {
  if (!dragging) return
  event.preventDefault()
  const delta = event.clientX - lastX
  if (!delta) return
  lastX = event.clientX
  emit('resize', delta)
}

function onPointerUp() {
  dragging = false
  layoutStore.endColumnResize()
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

onBeforeUnmount(onPointerUp)
</script>

<template>
  <div
    class="muse-resize-handle"
    role="separator"
    aria-orientation="vertical"
    :aria-label="`${left}-${right}`"
    data-testid="agent-resize-handle"
    @pointerdown.prevent="onPointerDown"
  />
</template>
