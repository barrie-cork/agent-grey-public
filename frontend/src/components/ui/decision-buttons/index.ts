export { default as DecisionButtons } from './DecisionButtons.vue'

export type Decision = 'include' | 'exclude' | 'maybe'

export interface DecisionButtonsProps {
  currentDecision?: Decision
  disabled?: boolean
  loading?: boolean
}
