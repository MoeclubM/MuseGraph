<script setup lang="ts">
import { computed } from 'vue'
import { Check } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    currentStep: number
    completedSteps: number[]
    projectHasGraph?: boolean
    simulationStatus?: string
  }>(),
  {
    projectHasGraph: false,
    simulationStatus: '',
  }
)

const steps = computed(() => [
  {
    num: 1,
    label: 'Graph Build',
    description: 'Knowledge Graph',
    isComplete: props.projectHasGraph || props.completedSteps.includes(1),
  },
  {
    num: 2,
    label: 'Prepare',
    description: 'Environment Setup',
    isComplete: props.simulationStatus === 'ready' || props.completedSteps.includes(2),
  },
  {
    num: 3,
    label: 'Run',
    description: 'Simulation Run',
    isComplete: props.completedSteps.includes(3),
  },
  {
    num: 4,
    label: 'Report',
    description: 'Report Generation',
    isComplete: props.completedSteps.includes(4),
  },
  {
    num: 5,
    label: 'Interaction',
    description: 'Deep Interaction',
    isComplete: props.completedSteps.includes(5),
  },
])

function getStepStatus(num: number) {
  const step = steps.value.find(s => s.num === num)
  if (step?.isComplete) return 'completed'
  if (num === props.currentStep) return 'active'
  return 'pending'
}
</script>

<template>
  <div class="w-full">
    <!-- Step indicator bar -->
    <div class="flex items-center justify-between relative">
      <!-- Progress line background -->
      <div class="absolute top-5 left-0 right-0 h-0.5 bg-stone-300 dark:bg-zinc-700" />

      <!-- Progress line fill -->
      <div
        class="absolute top-5 left-0 h-0.5 bg-[#FF5722] transition-all duration-500"
        :style="{ width: `${((currentStep - 1) / 4) * 100}%` }"
      />

      <!-- Step circles -->
      <div
        v-for="step in steps"
        :key="step.num"
        class="relative z-10 flex flex-col items-center"
      >
        <div
          :class="[
            'w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium transition-all duration-300',
            {
              'bg-[#FF5722] text-white shadow-lg shadow-orange-500/30': getStepStatus(step.num) === 'completed',
              'border-2 border-[#FF5722] bg-stone-100 text-[#FF5722] animate-pulse dark:bg-zinc-900': getStepStatus(step.num) === 'active',
              'border-2 border-stone-400 bg-stone-100 text-stone-500 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-500': getStepStatus(step.num) === 'pending',
            }
          ]"
        >
          <Check v-if="getStepStatus(step.num) === 'completed'" class="w-5 h-5" />
          <span v-else>{{ step.num }}</span>
        </div>

        <!-- Step labels -->
        <div class="mt-3 text-center">
          <div
            :class="[
              'text-xs font-medium transition-colors',
              getStepStatus(step.num) === 'completed' ? 'text-[#FF5722]' :
              getStepStatus(step.num) === 'active' ? 'text-stone-800 dark:text-zinc-100' : 'text-stone-500 dark:text-zinc-500'
            ]"
          >
            {{ step.label }}
          </div>
          <div class="text-[10px] text-stone-500 dark:text-zinc-500 mt-0.5 hidden sm:block">
            {{ step.description }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
