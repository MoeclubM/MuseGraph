<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import type { SimulationRuntime } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'

const props = defineProps<{
  visible: boolean
  simulationLoading: boolean
  simulationCreating: boolean
  graphReady: boolean
  simulationError: string | null
  projectSimulations: SimulationRuntime[]
  confirmedSimulationId: string
  canConfirmSimulation: (sim: SimulationRuntime) => boolean
}>()

const emit = defineEmits<{
  refresh: []
  create: []
  confirm: [simulationId: string]
  openSimulation: [simulationId: string]
}>()
</script>

<template>
  <Card v-show="visible" class="space-y-2">
    <div class="flex items-center justify-between">
      <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">Workflow</h3>
      <Button variant="ghost" size="sm" :loading="props.simulationLoading" @click="emit('refresh')">
        Refresh
      </Button>
    </div>
    <p class="text-xs text-stone-500 dark:text-zinc-500">
      Continue workflow: graph analysis -> create simulation -> confirm simulation -> run continue.
    </p>
    <Button
      variant="secondary"
      class="w-full"
      :loading="props.simulationCreating"
      :disabled="!props.graphReady"
      @click="emit('create')"
    >
      <Sparkles class="w-4 h-4" />
      Create Simulation
    </Button>
    <p v-if="!props.graphReady" class="text-xs text-amber-700 dark:text-amber-300">
      Build graph first, then create workflow simulation.
    </p>
    <Alert v-if="props.simulationError" variant="destructive" class="text-sm">
      {{ props.simulationError }}
    </Alert>
    <div v-if="props.projectSimulations.length > 0" class="space-y-1.5 max-h-52 overflow-y-auto">
      <div
        v-for="sim in props.projectSimulations.slice(0, 8)"
        :key="sim.simulation_id"
        class="rounded-lg border border-stone-300/70 dark:border-zinc-700/50 bg-stone-100/75 dark:bg-zinc-800/40 px-3 py-2"
      >
        <div class="flex items-center justify-between gap-2">
          <Button
            variant="ghost"
            size="sm"
            class="h-auto min-w-0 justify-start px-0 py-0 text-left hover:bg-transparent dark:hover:bg-transparent"
            @click="emit('openSimulation', sim.simulation_id)"
          >
            <p class="text-xs font-medium text-stone-700 dark:text-zinc-300">{{ sim.simulation_id.slice(0, 12) }}...</p>
            <p class="mt-1 text-[11px] text-stone-500 dark:text-zinc-500">{{ sim.updated_at || sim.created_at || '-' }}</p>
          </Button>
          <div class="flex items-center gap-2">
            <span class="text-xs text-stone-500 dark:text-zinc-500 capitalize">{{ sim.status }}</span>
            <Button
              variant="secondary"
              size="sm"
              class="h-auto px-2 py-1 text-[11px]"
              :class="
                props.confirmedSimulationId === sim.simulation_id
                  ? 'border-emerald-600 bg-emerald-900/20 text-emerald-700 dark:text-emerald-300'
                  : props.canConfirmSimulation(sim)
                    ? 'border-amber-600/70 text-amber-700 dark:text-amber-300 hover:border-amber-500'
                    : 'border-stone-300 dark:border-zinc-700 text-stone-500 dark:text-zinc-500 cursor-not-allowed'
              "
              :disabled="!props.canConfirmSimulation(sim)"
              @click="emit('confirm', sim.simulation_id)"
            >
              {{ props.confirmedSimulationId === sim.simulation_id ? 'Confirmed' : 'Confirm' }}
            </Button>
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>
