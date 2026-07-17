<script setup lang="ts">
import type { CSSProperties } from 'vue'
import { useI18n } from 'vue-i18n'
import Button from '@/components/ui/Button.vue'

const props = defineProps<{
  visible: boolean
  style: CSSProperties
}>()

const emit = defineEmits<{
  rename: []
  delete: []
}>()

const { t } = useI18n()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      data-agent-explorer-context-menu="true"
      class="fixed z-[90] w-44 rounded-md border border-stone-300 bg-stone-50 p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
      :style="props.style"
      @contextmenu.prevent
    >
      <Button
        variant="ghost"
        size="sm"
        class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-stone-700 dark:text-zinc-200"
        data-testid="agent-explorer-context-rename"
        @click="emit('rename')"
      >
        {{ t('agent.editor.contextRename') }}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-300 dark:hover:bg-red-900/20 dark:hover:text-red-200"
        data-testid="agent-explorer-context-delete"
        @click="emit('delete')"
      >
        {{ t('agent.editor.contextDelete') }}
      </Button>
    </div>
  </Teleport>
</template>
