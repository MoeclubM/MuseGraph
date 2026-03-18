<script setup lang="ts">
import { Save } from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'

const props = defineProps<{
  projectTitleEditing: boolean
  projectTitleDraft: string
  projectTitleSaving: boolean
  projectTitle: string
  leftPanelCollapsed: boolean
  rightPanelCollapsed: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  'update:projectTitleDraft': [value: string]
  beginEditTitle: []
  submitTitle: []
  cancelTitle: []
  toggleLeftPanel: []
  toggleRightPanel: []
  save: []
}>()
</script>

<template>
  <div class="flex items-center justify-between gap-3 border-b border-stone-300/80 bg-stone-100/80 px-4 py-3 dark:border-zinc-700/60 dark:bg-zinc-900/40">
    <div class="min-w-0 flex-1">
      <div v-if="projectTitleEditing" class="flex flex-wrap items-center gap-2">
        <Input
          :model-value="projectTitleDraft"
          class="w-full max-w-sm"
          placeholder="Project title"
          :disabled="projectTitleSaving"
          @update:modelValue="(value) => emit('update:projectTitleDraft', String(value || ''))"
          @keydown.enter.prevent="emit('submitTitle')"
          @keydown.esc.prevent="emit('cancelTitle')"
        />
        <Button
          variant="secondary"
          size="sm"
          :loading="projectTitleSaving"
          @click="emit('submitTitle')"
        >
          Save
        </Button>
        <Button
          variant="ghost"
          size="sm"
          :disabled="projectTitleSaving"
          @click="emit('cancelTitle')"
        >
          Cancel
        </Button>
      </div>
      <Button
        v-else
        variant="ghost"
        size="sm"
        class="h-auto min-h-0 px-0 py-0 text-left hover:bg-transparent dark:hover:bg-transparent"
        @click="emit('beginEditTitle')"
      >
        <h1 class="truncate text-sm font-semibold sm:text-base">
          {{ projectTitle }}
        </h1>
      </Button>
    </div>
    <div class="flex flex-wrap items-center justify-end gap-2 sm:flex-nowrap">
      <Button variant="secondary" size="sm" @click="emit('toggleLeftPanel')">
        {{ leftPanelCollapsed ? 'Show Files' : 'Hide Files' }}
      </Button>
      <Button variant="secondary" size="sm" @click="emit('toggleRightPanel')">
        {{ rightPanelCollapsed ? 'Show AI' : 'Hide AI' }}
      </Button>
      <Button variant="secondary" size="sm" :loading="saving" @click="emit('save')">
        <Save class="w-4 h-4" />
        Save
      </Button>
    </div>
  </div>
</template>
