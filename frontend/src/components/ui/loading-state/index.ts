export { default as LoadingState } from './LoadingState.vue'

export type LoadingVariant = 'spinner' | 'skeleton' | 'card' | 'table'

export interface LoadingStateProps {
  variant?: LoadingVariant
  lines?: number
}
