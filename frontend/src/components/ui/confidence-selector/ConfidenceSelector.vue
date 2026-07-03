<script setup lang="ts">
import { Label } from '@/components/ui/label'

interface Props {
  modelValue?: number
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: 2,
  disabled: false
})

const emit = defineEmits<{
  'update:modelValue': [value: number]
}>()

function setConfidence(level: number) {
  if (props.disabled) return
  emit('update:modelValue', level)
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <Label class="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Reviewer Confidence</Label>
    </div>
    <div 
      class="inline-flex rounded-sm border border-scholar p-0.5 w-full transition-colors"
      :class="disabled ? 'bg-muted/10 opacity-50 cursor-not-allowed' : 'bg-muted/30'"
    >
      <button
        type="button"
        @click="setConfidence(1)"
        :disabled="disabled"
        class="flex-1 text-[10px] uppercase tracking-widest font-bold py-1.5 rounded-sm transition-colors text-center"
        :class="modelValue === 1 ? 'bg-background shadow-sm text-warning-dark border border-scholar/50' : 'text-muted-foreground hover:text-foreground'"
      >
        Low
      </button>
      <button
        type="button"
        @click="setConfidence(2)"
        :disabled="disabled"
        class="flex-1 text-[10px] uppercase tracking-widest font-bold py-1.5 rounded-sm transition-colors text-center"
        :class="modelValue === 2 ? 'bg-background shadow-sm text-info-dark border border-scholar/50' : 'text-muted-foreground hover:text-foreground'"
      >
        Medium
      </button>
      <button
        type="button"
        @click="setConfidence(3)"
        :disabled="disabled"
        class="flex-1 text-[10px] uppercase tracking-widest font-bold py-1.5 rounded-sm transition-colors text-center"
        :class="modelValue === 3 ? 'bg-background shadow-sm text-success-dark border border-scholar/50' : 'text-muted-foreground hover:text-foreground'"
      >
        High
      </button>
    </div>
  </div>
</template>
