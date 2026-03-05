<script setup lang="ts">
import type { CSSProperties } from 'vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps<{
  visible: boolean
  style: CSSProperties
  inScope: boolean
}>()

const emit = defineEmits<{
  open: []
  rename: []
  toggleScope: []
  delete: []
}>()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      data-chapter-context-menu="true"
      class="fixed z-[90] w-48 rounded-lg border border-stone-300 bg-stone-50 p-1 shadow-xl dark:border-zinc-700 dark:bg-zinc-800"
      :style="props.style"
      @contextmenu.prevent
    >
      <Button
        variant="ghost"
        size="sm"
        class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-stone-700 dark:text-zinc-200"
        @click="emit('open')"
      >
        打开章节
      </Button>
      <Button
        variant="ghost"
        size="sm"
        class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-stone-700 dark:text-zinc-200"
        @click="emit('rename')"
      >
        重命名章节
      </Button>
      <Button
        variant="ghost"
        size="sm"
        class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-stone-700 dark:text-zinc-200"
        @click="emit('toggleScope')"
      >
        {{ props.inScope ? '移出流程范围' : '加入流程范围' }}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-300 dark:hover:bg-red-900/20 dark:hover:text-red-200"
        @click="emit('delete')"
      >
        删除章节
      </Button>
    </div>
  </Teleport>
</template>
