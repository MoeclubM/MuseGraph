<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ChevronRight, Loader2, Search } from '@lucide/vue'
import { cn } from '@/lib/utils'
import type { EntityCategory, EntityRecord, ProjectFact } from '@/api/facts'
import { listProjectFacts, searchProjectEntities } from '@/api/facts'
import SearchInput from '@/components/ui/SearchInput.vue'
import { collectProjectEntities, formatEntityAttributeValue, groupEntitiesByType } from '@/utils/dynamicOntology'
import type { AgentWorkspace, ProjectOntology } from '@/types'

const props = defineProps<{
  projectId: string
  workspace: AgentWorkspace
  ontology?: ProjectOntology | null
}>()

const { t } = useI18n()

const facts = ref<ProjectFact[]>([])
const factsLoading = ref(false)
const factsError = ref<string | null>(null)

const entitySearchQuery = ref('')
const entitySearchLoading = ref(false)
const entitySearchError = ref<string | null>(null)
const entitySearchResults = ref<EntityRecord[]>([])
const entitySearchMode = ref(false)

const expandedCategories = ref<Record<string, boolean>>({})

const structuredMemory = computed(() =>
  props.workspace.structured_memory && typeof props.workspace.structured_memory === 'object'
    ? props.workspace.structured_memory
    : {},
)

const memorySchema = computed(() =>
  props.workspace.memory_schema && typeof props.workspace.memory_schema === 'object'
    ? props.workspace.memory_schema
    : {},
)

const factGraph = computed(() =>
  props.workspace.fact_graph && typeof props.workspace.fact_graph === 'object'
    ? (props.workspace.fact_graph as { nodes?: Record<string, unknown>[] })
    : undefined,
)

const allEntities = computed(() =>
  collectProjectEntities({
    facts: facts.value,
    structuredMemory: structuredMemory.value,
    memorySchema: memorySchema.value,
    factGraph: factGraph.value,
    ontology: props.ontology,
  }),
)

const categories = computed<EntityCategory[]>(() => groupEntitiesByType(allEntities.value))

const displayedCategories = computed(() => {
  if (entitySearchMode.value && entitySearchQuery.value.trim()) {
    return groupEntitiesByType(entitySearchResults.value)
  }
  return categories.value
})

const ontologyEntityTypes = computed(() => props.ontology?.entity_types || [])

function memoryStatusLabel(status: string): string {
  const key = `agent.entities.memoryStatus.${status}`
  const translated = t(key)
  return translated === key ? status : translated
}

async function loadFacts() {
  if (!props.projectId) return
  factsLoading.value = true
  factsError.value = null
  try {
    facts.value = await listProjectFacts(props.projectId)
  } catch (error) {
    facts.value = []
    factsError.value = error instanceof Error ? error.message : t('agent.entities.loadFactsFailed')
  } finally {
    factsLoading.value = false
  }
}

async function handleEntitySearch() {
  const query = entitySearchQuery.value.trim()
  if (!query) {
    entitySearchMode.value = false
    entitySearchResults.value = []
    entitySearchError.value = null
    return
  }
  entitySearchLoading.value = true
  entitySearchError.value = null
  entitySearchMode.value = true
  try {
    const response = await searchProjectEntities(props.projectId, query, { limit: 30 })
    entitySearchResults.value = response.results
  } catch (error) {
    entitySearchResults.value = []
    entitySearchError.value = error instanceof Error ? error.message : t('agent.entities.searchFailed')
  } finally {
    entitySearchLoading.value = false
  }
}

function toggleCategory(type: string) {
  expandedCategories.value[type] = !expandedCategories.value[type]
}

function isCategoryExpanded(type: string): boolean {
  return expandedCategories.value[type] !== false
}

function attributeEntries(entity: EntityRecord): Array<[string, string]> {
  return Object.entries(entity.attributes || {})
    .filter(([key, value]) => key && value !== undefined && value !== null && value !== '')
    .map(([key, value]) => [key, formatEntityAttributeValue(value)])
}

watch(
  () => props.projectId,
  () => {
    void loadFacts()
  },
  { immediate: true },
)

watch(categories, (next) => {
  for (const category of next) {
    if (expandedCategories.value[category.type] === undefined) {
      expandedCategories.value[category.type] = true
    }
  }
}, { immediate: true })

defineExpose({ reload: loadFacts })
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col" data-testid="agent-entities-panel">
    <div class="border-b border-[color:var(--muse-border)] p-3">
      <h3 class="text-sm font-semibold muse-text-heading">{{ t('agent.entities.title') }}</h3>
      <p class="mt-1 text-[11px] muse-text-faint">{{ t('agent.entities.subtitle') }}</p>

      <div v-if="ontologyEntityTypes.length" class="mt-2 flex flex-wrap gap-1.5">
        <span
          v-for="entityType in ontologyEntityTypes"
          :key="entityType.name"
          class="rounded-full border border-[color:var(--muse-border)] px-2 py-0.5 text-[10px] muse-text-muted"
        >
          {{ entityType.name }}
        </span>
      </div>

      <div class="mt-3 flex gap-2">
        <SearchInput
          v-model="entitySearchQuery"
          :placeholder="t('agent.entities.searchPlaceholder')"
          :aria-label="t('agent.entities.searchAriaLabel')"
          test-id="agent-entity-search-input"
          @search="handleEntitySearch"
        />
        <button
          type="button"
          class="muse-btn muse-btn-secondary shrink-0 px-2"
          :disabled="entitySearchLoading"
          data-testid="agent-entity-search-button"
          @click="handleEntitySearch"
        >
          <Loader2 v-if="entitySearchLoading" class="h-3.5 w-3.5 animate-spin" />
          <Search v-else class="h-3.5 w-3.5" />
        </button>
      </div>
      <p v-if="entitySearchError" class="mt-2 text-[11px] text-[color:var(--muse-danger)]">{{ entitySearchError }}</p>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto muse-workspace-scroll">
      <section class="border-b border-[color:var(--muse-border)] p-3">
        <div class="mb-2 flex items-center justify-between gap-2">
          <h4 class="text-xs font-semibold muse-text-heading">{{ t('agent.facts.title') }}</h4>
          <span class="text-[10px] muse-text-faint">{{ facts.length }}</span>
        </div>
        <p v-if="factsLoading" class="text-[11px] muse-text-muted">{{ t('agent.facts.loading') }}</p>
        <p v-else-if="factsError" class="text-[11px] text-[color:var(--muse-danger)]">{{ factsError }}</p>
        <p v-else-if="!facts.length" class="text-[11px] muse-text-faint">{{ t('agent.facts.empty') }}</p>
        <div v-else class="space-y-2">
          <article
            v-for="fact in facts"
            :key="fact.id"
            class="muse-card muse-card-inset p-2"
            data-testid="agent-fact-card"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="truncate text-xs font-medium muse-text-heading">{{ fact.title }}</p>
                <p class="mt-0.5 line-clamp-2 text-[11px] muse-text-muted">{{ fact.content }}</p>
              </div>
              <span class="shrink-0 rounded px-1.5 py-0.5 text-[10px] muse-text-faint">
                {{ memoryStatusLabel(fact.memory_status) }}
              </span>
            </div>
            <p v-if="fact.entities?.length" class="mt-1 text-[10px] muse-text-faint">
              {{ t('agent.facts.entityCount', { count: fact.entities.length }) }}
            </p>
          </article>
        </div>
      </section>

      <section class="p-3">
        <div class="mb-2 flex items-center justify-between gap-2">
          <h4 class="text-xs font-semibold muse-text-heading" data-testid="agent-ontology-categories">
            {{ t('agent.entities.categoriesTitle') }}
          </h4>
          <span class="text-[10px] muse-text-faint">
            {{ t('agent.entities.entityCount', { count: entitySearchMode ? entitySearchResults.length : allEntities.length }) }}
          </span>
        </div>

        <p v-if="!displayedCategories.length" class="text-[11px] muse-text-faint">
          {{ entitySearchMode ? t('agent.entities.noSearchResults') : t('agent.entities.empty') }}
        </p>

        <div v-else class="space-y-2">
          <section
            v-for="category in displayedCategories"
            :key="category.type"
            class="muse-card muse-card-inset overflow-hidden"
            data-testid="agent-entity-category"
          >
            <button
              type="button"
              class="flex w-full items-center gap-2 px-3 py-2 text-left"
              @click="toggleCategory(category.type)"
            >
              <component :is="isCategoryExpanded(category.type) ? ChevronDown : ChevronRight" class="h-3.5 w-3.5 muse-text-faint" />
              <span class="text-xs font-medium muse-text-heading">{{ category.label }}</span>
              <span class="ml-auto rounded-full bg-[color:var(--muse-surface-2)] px-2 py-0.5 text-[10px] muse-text-muted">
                {{ category.count }}
              </span>
            </button>

            <div v-if="isCategoryExpanded(category.type)" class="space-y-2 border-t border-[color:var(--muse-border)] p-2">
              <article
                v-for="entity in category.entities"
                :key="`${category.type}-${entity.id}`"
                class="rounded border border-[color:var(--muse-border)] p-2"
                data-testid="agent-entity-card"
              >
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="text-xs font-medium muse-text-heading">{{ entity.name }}</p>
                    <p v-if="entity.summary" class="mt-1 text-[11px] muse-text-muted">{{ entity.summary }}</p>
                  </div>
                  <span
                    :class="cn('shrink-0 rounded px-1.5 py-0.5 text-[10px]', 'bg-[color:var(--muse-surface-2)] muse-text-muted')"
                  >
                    {{ entity.type }}
                  </span>
                </div>
                <table v-if="attributeEntries(entity).length" class="mt-2 w-full text-[10px]">
                  <tbody>
                    <tr
                      v-for="[key, value] in attributeEntries(entity)"
                      :key="key"
                      class="border-t border-[color:var(--muse-border)]"
                    >
                      <td class="py-1 pr-2 align-top font-medium muse-text-faint">{{ key }}</td>
                      <td class="py-1 align-top muse-text-muted">{{ value }}</td>
                    </tr>
                  </tbody>
                </table>
                <p v-if="entity.source" class="mt-1 text-[10px] muse-text-faint">{{ entity.source }}</p>
              </article>
            </div>
          </section>
        </div>
      </section>
    </div>
  </div>
</template>
