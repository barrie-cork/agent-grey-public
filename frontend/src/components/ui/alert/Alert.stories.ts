import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Alert, AlertTitle, AlertDescription } from '.'

const meta: Meta<typeof Alert> = {
  title: 'UI/Alert',
  component: Alert,
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['default', 'destructive'],
      description: 'Alert variant',
    },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => ({
    components: { Alert, AlertTitle, AlertDescription },
    template: `
      <Alert>
        <AlertTitle>Heads up!</AlertTitle>
        <AlertDescription>
          You can add components to your app using the CLI.
        </AlertDescription>
      </Alert>
    `,
  }),
}

export const Destructive: Story = {
  render: () => ({
    components: { Alert, AlertTitle, AlertDescription },
    template: `
      <Alert variant="destructive">
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>
          Your session has expired. Please log in again.
        </AlertDescription>
      </Alert>
    `,
  }),
}

export const WithIcon: Story = {
  render: () => ({
    components: { Alert, AlertTitle, AlertDescription },
    template: `
      <Alert>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="size-4">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
        <AlertTitle>Information</AlertTitle>
        <AlertDescription>
          This alert includes an icon for added visual context.
        </AlertDescription>
      </Alert>
    `,
  }),
}

export const AllVariants: Story = {
  render: () => ({
    components: { Alert, AlertTitle, AlertDescription },
    template: `
      <div class="space-y-4">
        <Alert>
          <AlertTitle>Default Alert</AlertTitle>
          <AlertDescription>This is a default alert for general information.</AlertDescription>
        </Alert>
        <Alert variant="destructive">
          <AlertTitle>Destructive Alert</AlertTitle>
          <AlertDescription>This is a destructive alert for error states.</AlertDescription>
        </Alert>
      </div>
    `,
  }),
}
