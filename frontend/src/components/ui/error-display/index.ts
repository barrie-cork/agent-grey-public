export { default as ErrorDisplay } from './ErrorDisplay.vue'

export interface ErrorDisplayProps {
  error: string | Error
  dismissible?: boolean
  retry?: boolean
  title?: string
}
