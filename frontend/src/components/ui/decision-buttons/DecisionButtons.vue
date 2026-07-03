<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { Button } from '@/components/ui/button'
import { CheckCircle, XCircle, HelpCircle } from 'lucide-vue-next'
import type { Decision } from '.'

interface Props {
  currentDecision?: Decision
  disabled?: boolean
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  loading: false
})

const emit = defineEmits<{
  decision: [value: Decision]
}>()

function handleDecision(decision: Decision) {
  if (props.disabled || props.loading) return
  emit('decision', decision)
}

function handleKeydown(event: KeyboardEvent) {
  if (props.disabled || props.loading) return
  // Ignore if user is typing in an input field
  const target = event.target as HTMLElement
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
    return
  }

  const key = event.key.toLowerCase()
  if (key === 'i') handleDecision('include')
  else if (key === 'e') handleDecision('exclude')
  else if (key === 'm') handleDecision('maybe')
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div
    role="group"
    aria-label="Decision Matrix"
    class="flex flex-col gap-2"
  >
    <Button
      variant="outline"
      data-testid="include-btn"
      :disabled="disabled || loading"
      class="h-10 text-xs font-bold transition-all justify-start px-3 shadow-none rounded-sm border-scholar hover:bg-muted"
      :class="currentDecision === 'include' ? 'border-l-4 border-l-success bg-success/10 text-success-dark hover:bg-success/20' : 'text-foreground'"
      @click="handleDecision('include')"
    >
      <div class="flex items-center justify-between w-full">
        <div class="flex items-center">
          <CheckCircle :size="16" class="mr-2" :class="currentDecision === 'include' ? 'text-success' : 'text-muted-foreground'" />
          Include
        </div>
        <kbd class="text-[9px] px-1.5 py-0.5 border border-scholar rounded bg-white text-muted-foreground font-mono">I</kbd>
      </div>
    </Button>

    <Button
      variant="outline"
      data-testid="exclude-btn"
      :disabled="disabled || loading"
      class="h-10 text-xs font-bold transition-all justify-start px-3 shadow-none rounded-sm border-scholar hover:bg-muted"
      :class="currentDecision === 'exclude' ? 'border-l-4 border-l-destructive bg-destructive/10 text-destructive-dark hover:bg-destructive/20' : 'text-foreground'"
      @click="handleDecision('exclude')"
    >
      <div class="flex items-center justify-between w-full">
        <div class="flex items-center">
          <XCircle :size="16" class="mr-2" :class="currentDecision === 'exclude' ? 'text-destructive' : 'text-muted-foreground'" />
          Exclude
        </div>
        <kbd class="text-[9px] px-1.5 py-0.5 border border-scholar rounded bg-white text-muted-foreground font-mono">E</kbd>
      </div>
    </Button>

    <Button
      variant="outline"
      data-testid="maybe-btn"
      :disabled="disabled || loading"
      class="h-10 text-xs font-bold transition-all justify-start px-3 shadow-none rounded-sm border-scholar hover:bg-muted"
      :class="currentDecision === 'maybe' ? 'border-l-4 border-l-warning bg-warning/10 text-warning-dark hover:bg-warning/20' : 'text-foreground'"
      @click="handleDecision('maybe')"
    >
      <div class="flex items-center justify-between w-full">
        <div class="flex items-center">
          <HelpCircle :size="16" class="mr-2" :class="currentDecision === 'maybe' ? 'text-warning' : 'text-muted-foreground'" />
          Maybe
        </div>
        <kbd class="text-[9px] px-1.5 py-0.5 border border-scholar rounded bg-white text-muted-foreground font-mono">M</kbd>
      </div>
    </Button>
  </div>
</template>
