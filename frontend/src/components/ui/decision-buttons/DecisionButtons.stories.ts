import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import DecisionButtons from './DecisionButtons.vue'
import type { Decision } from '.'

const meta: Meta<typeof DecisionButtons> = {
  title: 'UI/DecisionButtons',
  component: DecisionButtons,
  tags: ['autodocs'],
  argTypes: {
    currentDecision: {
      control: 'select',
      options: [undefined, 'include', 'exclude', 'maybe'],
      description: 'Currently selected decision',
    },
    disabled: {
      control: 'boolean',
      description: 'Disable all buttons',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading state',
    },
  },
  parameters: {
    docs: {
      description: {
        component:
          'Decision buttons for screening workflow. Supports keyboard shortcuts: I (Include), E (Exclude), M (Maybe).',
      },
    },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: (args) => ({
    components: { DecisionButtons },
    setup() {
      return { args }
    },
    template: '<DecisionButtons v-bind="args" />',
  }),
}

export const Interactive: Story = {
  render: () => ({
    components: { DecisionButtons },
    setup() {
      const decision = ref<Decision | undefined>(undefined)
      const handleDecision = (value: Decision) => {
        decision.value = value
      }
      return { decision, handleDecision }
    },
    template: `
      <div class="space-y-4">
        <DecisionButtons
          :current-decision="decision"
          @decision="handleDecision"
        />
        <p class="text-sm text-muted-foreground">
          Selected: {{ decision || 'None' }}
        </p>
        <p class="text-xs text-muted-foreground">
          Try keyboard shortcuts: I, E, or M
        </p>
      </div>
    `,
  }),
}

export const IncludeSelected: Story = {
  args: {
    currentDecision: 'include',
  },
  render: (args) => ({
    components: { DecisionButtons },
    setup() {
      return { args }
    },
    template: '<DecisionButtons v-bind="args" />',
  }),
}

export const ExcludeSelected: Story = {
  args: {
    currentDecision: 'exclude',
  },
  render: (args) => ({
    components: { DecisionButtons },
    setup() {
      return { args }
    },
    template: '<DecisionButtons v-bind="args" />',
  }),
}

export const MaybeSelected: Story = {
  args: {
    currentDecision: 'maybe',
  },
  render: (args) => ({
    components: { DecisionButtons },
    setup() {
      return { args }
    },
    template: '<DecisionButtons v-bind="args" />',
  }),
}

export const Disabled: Story = {
  args: {
    disabled: true,
  },
  render: (args) => ({
    components: { DecisionButtons },
    setup() {
      return { args }
    },
    template: '<DecisionButtons v-bind="args" />',
  }),
}

export const Loading: Story = {
  args: {
    loading: true,
  },
  render: (args) => ({
    components: { DecisionButtons },
    setup() {
      return { args }
    },
    template: '<DecisionButtons v-bind="args" />',
  }),
}

export const AllStates: Story = {
  render: () => ({
    components: { DecisionButtons },
    template: `
      <div class="space-y-6">
        <div>
          <p class="text-sm font-medium mb-2">Default</p>
          <DecisionButtons />
        </div>
        <div>
          <p class="text-sm font-medium mb-2">Include selected</p>
          <DecisionButtons current-decision="include" />
        </div>
        <div>
          <p class="text-sm font-medium mb-2">Exclude selected</p>
          <DecisionButtons current-decision="exclude" />
        </div>
        <div>
          <p class="text-sm font-medium mb-2">Maybe selected</p>
          <DecisionButtons current-decision="maybe" />
        </div>
        <div>
          <p class="text-sm font-medium mb-2">Disabled</p>
          <DecisionButtons disabled />
        </div>
      </div>
    `,
  }),
}
