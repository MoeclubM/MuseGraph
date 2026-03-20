<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { TabsTrigger, type TabsTriggerProps, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<TabsTriggerProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = computed(() => {
  const { class: _, ...rest } = props
  return rest
})

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <TabsTrigger
    v-bind="forwarded"
    :class="
      cn(
        'inline-flex h-[calc(100%-1px)] items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-transparent px-3 py-1.5 text-sm font-medium transition-[color,box-shadow]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60',
        'disabled:pointer-events-none disabled:opacity-50',
        'data-[state=active]:bg-stone-50 data-[state=active]:text-amber-700',
        'dark:data-[state=active]:bg-zinc-700 dark:data-[state=active]:text-amber-300',
        props.class
      )
    "
  >
    <slot />
  </TabsTrigger>
</template>
