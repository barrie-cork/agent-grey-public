export { default as ResultCard } from './ResultCard.vue'
export type { SearchResult } from './ResultCard.vue'

export interface ResultCardProps {
  result: import('./ResultCard.vue').SearchResult
  showDecision?: boolean
}
