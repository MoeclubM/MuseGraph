<script setup lang="ts">
import { computed, type Component } from 'vue'
import Alert from '@/components/ui/Alert.vue'
import Button from '@/components/ui/Button.vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

type RightPanelTabKey = 'graph' | 'ai' | 'oasis'

const props = defineProps<{
  rightPanelCollapsed: boolean
  isMobileLayout: boolean
  rightPanelTab: RightPanelTabKey
  rightPanelTabs: Array<{ key: RightPanelTabKey; label: string; icon: Component }>
  graphReady: boolean
}>()

const emit = defineEmits<{
  'update:rightPanelTab': [value: RightPanelTabKey]
}>()

const rightPanelTabValue = computed({
  get: () => props.rightPanelTab,
  set: (value: RightPanelTabKey) => emit('update:rightPanelTab', value),
})

function switchToGraphTab() {
  emit('update:rightPanelTab', 'graph')
}
</script>

<template>
  <div
    class="shrink-0 flex flex-col overflow-hidden transition-all duration-200 bg-[#f7f3ea] dark:bg-zinc-900/70"
    :class="
      rightPanelCollapsed
        ? 'w-0 min-w-0 max-w-0'
        : (isMobileLayout ? 'w-full min-w-0 max-w-none' : 'w-[min(46vw,720px)] min-w-[360px] max-w-[720px]')
    "
  >
    <div class="space-y-3 border-b border-stone-300/70 px-5 py-5 dark:border-zinc-700/50">
      <div>
        <p class="text-[11px] uppercase tracking-[0.16em] text-stone-500 dark:text-zinc-400">
          AI Operations
        </p>
        <p class="text-base font-semibold text-stone-800 dark:text-zinc-100">
          {{ rightPanelTabs.map((tab) => tab.label).join(' · ') }}
        </p>
      </div>
      <Tabs v-model="rightPanelTabValue" class="w-full">
        <TabsList class="grid h-auto w-full grid-cols-3 gap-1 rounded-md border border-stone-200/90 bg-stone-100/90 p-1 dark:border-zinc-700/70 dark:bg-zinc-800/80">
          <TabsTrigger
            v-for="tab in rightPanelTabs"
            :key="tab.key"
            :value="tab.key"
            class="py-2.5"
          >
            <component :is="tab.icon" class="h-3.5 w-3.5" />
            {{ tab.label }}
          </TabsTrigger>
        </TabsList>
      </Tabs>
    </div>

    <div v-show="rightPanelTabValue !== 'graph'" class="flex-1 overflow-y-auto p-5 lg:p-6 space-y-5">
      <Alert
        v-if="!graphReady && rightPanelTabValue === 'oasis'"
        variant="warning"
      >
        OASIS needs graph context first.
        <Button
          variant="ghost"
          size="sm"
          class="ml-1 h-auto px-0 py-0 underline decoration-dotted hover:bg-transparent hover:text-amber-700 dark:hover:bg-transparent dark:hover:text-amber-100"
          @click="switchToGraphTab"
        >
          Go to graph
        </Button>
      </Alert>

      <slot name="ai-content" />
    </div>

    <div v-show="rightPanelTabValue !== 'ai'" class="flex-1 overflow-y-auto p-5 lg:p-6 space-y-5 border-t border-stone-300/60 dark:border-zinc-700/40">
      <slot name="graph-content" />
    </div>
  </div>
</template>
