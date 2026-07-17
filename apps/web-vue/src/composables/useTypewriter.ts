import { ref, watch, onUnmounted } from 'vue'

export function useTypewriter(
  source: () => string,
  options: { enabled?: () => boolean; charsPerTick?: number; intervalMs?: number } = {},
) {
  const displayed = ref('')
  let timer: ReturnType<typeof setInterval> | null = null
  const charsPerTick = options.charsPerTick ?? 3
  const intervalMs = options.intervalMs ?? 24

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function sync(flush = false) {
    const full = source() || ''
    const enabled = options.enabled?.() ?? true
    if (!enabled || flush) {
      stop()
      displayed.value = full
      return
    }
    if (displayed.value.length >= full.length) {
      if (displayed.value.length > full.length) displayed.value = full
      if (displayed.value === full) stop()
      return
    }
    if (timer) return
    timer = setInterval(() => {
      const target = source() || ''
      if (displayed.value.length >= target.length) {
        displayed.value = target
        stop()
        return
      }
      const next = Math.min(displayed.value.length + charsPerTick, target.length)
      displayed.value = target.slice(0, next)
    }, intervalMs)
  }

  watch(source, () => sync(false), { immediate: true })

  onUnmounted(stop)

  return { displayed, flush: () => sync(true) }
}
