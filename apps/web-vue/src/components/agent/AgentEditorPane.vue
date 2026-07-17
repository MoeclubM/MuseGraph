<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2, Save } from '@lucide/vue'
import TextEditor from '@/components/editor/TextEditor.vue'

const props = defineProps<{
  title: string
  breadcrumb: string
  modelValue: string
  placeholder: string
  readOnly: boolean
  dirty: boolean
  saving: boolean
  emptyMessage: string
  hasSelection: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'save': []
}>()

const { t } = useI18n()

const statusLabel = computed(() => {
  if (props.readOnly) return t('agent.editor.readOnly')
  if (props.saving) return t('common.saving')
  if (props.dirty) return t('agent.editor.pendingSave')
  return t('agent.editor.saved')
})

const statusClass = computed(() => {
  if (props.readOnly) return 'muse-text-faint'
  if (props.saving || props.dirty) return 'muse-text-accent'
  return 'muse-text-faint'
})
</script>

<template>
  <div class="muse-editor-pane" data-testid="agent-editor-pane">
    <div class="muse-editor-toolbar">
      <div class="min-w-0 flex-1">
        <p v-if="breadcrumb" class="truncate text-[10px] muse-text-faint">{{ breadcrumb }}</p>
        <div class="flex min-w-0 items-center gap-2">
          <span
            v-if="hasSelection && dirty && !readOnly"
            class="h-2 w-2 shrink-0 rounded-full bg-[color:var(--muse-accent)]"
            :title="t('agent.editor.pendingSave')"
          />
          <p class="min-w-0 truncate text-xs font-medium muse-text-body">
            {{ title || t('agent.editor.noFileSelected') }}
          </p>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <button
          v-if="hasSelection && dirty && !readOnly"
          type="button"
          class="muse-icon-btn !h-6 !w-6"
          :title="t('agent.editor.save')"
          :disabled="saving"
          @click="emit('save')"
        >
          <Save class="h-3.5 w-3.5" />
        </button>
        <Loader2 v-if="saving" class="h-3 w-3 animate-spin muse-text-accent" />
        <span class="text-[11px]" :class="statusClass" data-testid="agent-editor-status">{{ statusLabel }}</span>
      </div>
    </div>

    <div class="muse-editor-content">
      <TextEditor
        v-if="hasSelection"
        :model-value="modelValue"
        :placeholder="placeholder"
        :readonly="readOnly"
        compact
        @update:model-value="emit('update:modelValue', $event)"
      />
      <div v-else class="muse-empty-state">
        <p class="text-xs muse-text-muted">{{ emptyMessage }}</p>
      </div>
    </div>
  </div>
</template>
