<script setup lang="ts">
/**
 * StatusBadge - Re-exported from Phase 04 UI component
 *
 * This file re-exports the Phase 04 StatusBadge component for backward compatibility.
 * The Phase 04 version supports both the old API (uppercase status values like 'INCLUDE',
 * 'PENDING', variant prop) and the new API (lowercase status values).
 *
 * Usage remains the same:
 *   <StatusBadge status="PENDING" variant="conflict" size="small" />
 *   <StatusBadge status="include" size="sm" />
 */
import { StatusBadge } from '@/components/ui/status-badge'

// Re-export component with defineOptions for SFC
defineOptions({
  name: 'StatusBadge',
  inheritAttrs: true
})
</script>

<template>
  <StatusBadge v-bind="$attrs">
    <slot />
  </StatusBadge>
</template>
