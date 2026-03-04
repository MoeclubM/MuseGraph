<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { TabsList, type TabsListProps, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<TabsListProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = computed(() => {
  const { class: _, ...rest } = props
  return rest
})

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <TabsList
    v-bind="forwarded"
    :class="cn('inline-flex h-10 items-center justify-center rounded-lg border border-stone-300/80 bg-stone-100 p-[3px] text-stone-600 dark:border-zinc-700/60 dark:bg-zinc-800 dark:text-zinc-400', props.class)"
  >
    <slot />
  </TabsList>
</template>
