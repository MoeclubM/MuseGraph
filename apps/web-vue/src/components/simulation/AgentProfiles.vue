<script setup lang="ts">
import { computed } from 'vue'
import { User, Briefcase, MessageSquare, Sparkles } from 'lucide-vue-next'
import type { OasisAgentProfile } from '@/types'

const props = withDefaults(
  defineProps<{
    profiles: OasisAgentProfile[]
    selectedAgent: string | null
    interactive?: boolean
    maxDisplay?: number
  }>(),
  {
    interactive: false,
    maxDisplay: 0, // 0 means show all
  }
)

const emit = defineEmits<{
  (e: 'select', agent: OasisAgentProfile): void
}>()

const displayedProfiles = computed(() => {
  if (props.maxDisplay > 0) {
    return props.profiles.slice(0, props.maxDisplay)
  }
  return props.profiles
})

function getRoleBadgeClass(role: string) {
  const roleColors: Record<string, string> = {
    influencer: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700',
    activist: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700',
    expert: 'bg-stone-200 text-stone-700 border-stone-300 dark:bg-zinc-700/60 dark:text-zinc-200 dark:border-zinc-600',
    observer: 'bg-stone-200/80 text-stone-700 border-stone-300 dark:bg-zinc-700/50 dark:text-zinc-300 dark:border-zinc-600',
    participant: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-700',
  }
  return roleColors[role.toLowerCase()] || 'bg-stone-200/80 text-stone-700 border-stone-300 dark:bg-zinc-700/50 dark:text-zinc-300 dark:border-zinc-600'
}

function getInitials(name: string) {
  return name.slice(0, 2).toUpperCase()
}

function getStanceColor(stance: string) {
  if (stance.toLowerCase().includes('support') || stance.toLowerCase().includes('favor')) {
    return 'text-emerald-400'
  }
  if (stance.toLowerCase().includes('oppose') || stance.toLowerCase().includes('against')) {
    return 'text-red-400'
  }
  return 'text-amber-400'
}
</script>

<template>
  <div class="w-full">
    <div v-if="profiles.length === 0" class="text-sm text-stone-500 dark:text-zinc-500 py-4 text-center">
      No agent profiles yet
    </div>

    <div
      v-else
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
    >
      <button
        v-for="profile in displayedProfiles"
        :key="profile.name"
        :class="[
          'rounded-md border p-3 text-left transition-all',
          interactive ? 'cursor-pointer hover:bg-stone-200/60 dark:hover:bg-zinc-800/50' : 'cursor-default',
          selectedAgent === profile.name
            ? 'border-amber-500/70 bg-amber-100/70 dark:bg-amber-900/20'
            : 'border-stone-300/80 bg-stone-100/70 hover:border-stone-400 dark:border-zinc-700/50 dark:bg-zinc-800/30 dark:hover:border-zinc-600'
        ]"
        :disabled="!interactive"
        @click="interactive && emit('select', profile)"
      >
        <!-- Header: Avatar + Name + Role -->
        <div class="flex items-start gap-2.5">
          <div class="w-10 h-10 rounded-full bg-stone-300 dark:bg-zinc-700 flex items-center justify-center text-sm font-bold text-stone-700 dark:text-zinc-300 shrink-0 border border-stone-400 dark:border-zinc-600">
            {{ getInitials(profile.name) }}
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-medium text-sm text-stone-800 dark:text-zinc-100 truncate">{{ profile.name }}</span>
            </div>

            <!-- Role Badge -->
            <span
              :class="[
                'inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded text-[10px] font-medium border',
                getRoleBadgeClass(profile.role)
              ]"
            >
              <Briefcase class="w-2.5 h-2.5" />
              {{ profile.role }}
            </span>
          </div>
        </div>

        <!-- Persona -->
        <p class="mt-2.5 text-xs text-stone-500 dark:text-zinc-400 line-clamp-2">
          {{ profile.persona }}
        </p>

        <!-- Stance -->
        <div class="mt-2 flex items-center gap-1.5">
          <Sparkles class="w-3 h-3 text-stone-500 dark:text-zinc-500" />
          <span :class="['text-xs', getStanceColor(profile.stance)]">
            {{ profile.stance }}
          </span>
        </div>

        <!-- Likely Actions -->
        <div v-if="profile.likely_actions?.length" class="mt-2.5 flex flex-wrap gap-1">
          <span
            v-for="(action, idx) in profile.likely_actions.slice(0, 3)"
            :key="idx"
            class="px-1.5 py-0.5 rounded bg-stone-200/80 text-[10px] text-stone-600 dark:bg-zinc-700/50 dark:text-zinc-400"
          >
            {{ action }}
          </span>
          <span
            v-if="profile.likely_actions.length > 3"
            class="px-1.5 py-0.5 rounded bg-stone-200/80 text-[10px] text-stone-500 dark:bg-zinc-700/50 dark:text-zinc-500"
          >
            +{{ profile.likely_actions.length - 3 }}
          </span>
        </div>
      </button>
    </div>

    <!-- Show more indicator -->
    <div
      v-if="maxDisplay > 0 && profiles.length > maxDisplay"
      class="mt-3 text-center text-xs text-stone-500 dark:text-zinc-500"
    >
      Showing {{ maxDisplay }} / {{ profiles.length }} agents
    </div>
  </div>
</template>
