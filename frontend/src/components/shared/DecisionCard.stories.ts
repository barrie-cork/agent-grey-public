import type { Meta, StoryObj } from '@storybook/vue3-vite'
import DecisionCard from './DecisionCard.vue'

const mockReviewer = {
  id: '1',
  username: 'jsmith',
  first_name: 'John',
  last_name: 'Smith',
  email: 'john@example.com',
}

const mockDecision = {
  id: '1',
  decision: 'INCLUDE' as const,
  reviewer: mockReviewer,
  decided_at: new Date().toISOString(),
  exclusion_reason: null,
  notes: 'This document is highly relevant to our research question.',
  confidence_level: 'HIGH',
  time_spent_seconds: 145,
  report_accessed: true,
}

const meta: Meta<typeof DecisionCard> = {
  title: 'Shared/DecisionCard',
  component: DecisionCard,
  tags: ['autodocs'],
  argTypes: {
    isBlinded: { control: 'boolean' },
    showMetadata: { control: 'boolean' },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const IncludeDecision: Story = {
  args: {
    decision: mockDecision,
    isBlinded: false,
  },
}

export const ExcludeDecision: Story = {
  args: {
    decision: {
      ...mockDecision,
      decision: 'EXCLUDE' as const,
      exclusion_reason: 'Not relevant to research scope',
      notes: 'The document focuses on a different population.',
      confidence_level: 'MEDIUM',
    },
    isBlinded: false,
  },
}

export const MaybeDecision: Story = {
  args: {
    decision: {
      ...mockDecision,
      decision: 'MAYBE' as const,
      notes: 'Need to review the full document before making a final decision.',
      confidence_level: 'LOW',
    },
    isBlinded: false,
  },
}

export const BlindedReviewer: Story = {
  args: {
    decision: mockDecision,
    isBlinded: true,
  },
}

export const WithMetadata: Story = {
  args: {
    decision: mockDecision,
    isBlinded: false,
    showMetadata: true,
  },
}

export const MinimalDecision: Story = {
  args: {
    decision: {
      ...mockDecision,
      notes: null,
      exclusion_reason: null,
      confidence_level: null,
      time_spent_seconds: null,
      report_accessed: undefined,
    },
    isBlinded: false,
  },
}

export const AllDecisions: Story = {
  render: () => ({
    components: { DecisionCard },
    setup() {
      const decisions = [
        { ...mockDecision, decision: 'INCLUDE' as const },
        {
          ...mockDecision,
          id: '2',
          decision: 'EXCLUDE' as const,
          exclusion_reason: 'Out of scope',
          reviewer: { ...mockReviewer, id: '2', first_name: 'Mary', last_name: 'Jones' },
        },
        {
          ...mockDecision,
          id: '3',
          decision: 'MAYBE' as const,
          notes: 'Needs further review',
          reviewer: { ...mockReviewer, id: '3', first_name: 'Bob', last_name: 'Williams' },
        },
      ]
      return { decisions }
    },
    template: `
      <div class="space-y-4">
        <DecisionCard
          v-for="d in decisions"
          :key="d.id"
          :decision="d"
          :is-blinded="false"
        />
      </div>
    `,
  }),
}
