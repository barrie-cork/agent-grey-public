<script setup lang="ts">
import { Skeleton } from '@/components/ui/skeleton'
import { Loader2 } from 'lucide-vue-next'
import type { LoadingVariant } from '.'

interface Props {
  variant?: LoadingVariant
  lines?: number
}

withDefaults(defineProps<Props>(), {
  variant: 'spinner',
  lines: 3
})
</script>

<template>
  <div
    role="status"
    aria-live="polite"
    aria-label="Loading"
    class="w-full"
  >
    <!-- Spinner -->
    <div
      v-if="variant === 'spinner'"
      class="flex items-center justify-center p-8"
    >
      <Loader2 :size="32" class="animate-spin text-primary" />
      <span class="ml-3 text-muted-foreground">Loading...</span>
    </div>

    <!-- Skeleton Lines -->
    <div
      v-else-if="variant === 'skeleton'"
      class="space-y-2"
    >
      <Skeleton
        v-for="i in lines"
        :key="i"
        :class="[
          'h-4',
          i === lines ? 'w-2/3' : 'w-full'
        ]"
      />
    </div>

    <!-- Card Skeleton -->
    <div
      v-else-if="variant === 'card'"
      class="border rounded-lg p-6 space-y-4"
    >
      <Skeleton class="h-6 w-1/3" />
      <Skeleton class="h-4 w-full" />
      <Skeleton class="h-4 w-full" />
      <Skeleton class="h-4 w-2/3" />
      <div class="flex gap-2 mt-4">
        <Skeleton class="h-9 w-24" />
        <Skeleton class="h-9 w-24" />
      </div>
    </div>

    <!-- Table Skeleton -->
    <div
      v-else-if="variant === 'table'"
      class="space-y-2"
    >
      <Skeleton class="h-10 w-full" />
      <Skeleton
        v-for="i in 5"
        :key="i"
        class="h-16 w-full"
      />
    </div>
  </div>
</template>
