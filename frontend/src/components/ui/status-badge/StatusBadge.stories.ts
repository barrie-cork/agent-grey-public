import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { StatusBadge } from '.'

const meta: Meta<typeof StatusBadge> = {
  title: 'UI/StatusBadge',
  component: StatusBadge,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'select',
      options: [
        'include', 'exclude', 'maybe',
        'pending', 'conflict', 'active', 'inactive',
        'INCLUDE', 'EXCLUDE', 'MAYBE',
        'PENDING', 'IN_DISCUSSION', 'RESOLVED', 'ESCALATED',
        'PROPOSED', 'ACCEPTED', 'IN_PROGRESS', 'COMPLETED', 'REJECTED', 'EXPIRED'
      ],
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
    },
    showIcon: { control: 'boolean' },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Include: Story = {
  args: { status: 'include' },
}

export const Exclude: Story = {
  args: { status: 'exclude' },
}

export const Maybe: Story = {
  args: { status: 'maybe' },
}

export const Pending: Story = {
  args: { status: 'pending' },
}

export const Conflict: Story = {
  args: { status: 'conflict' },
}

export const NoIcon: Story = {
  args: { status: 'include', showIcon: false },
}

export const Sizes: Story = {
  render: () => ({
    components: { StatusBadge },
    template: `
      <div class="flex items-center gap-4">
        <StatusBadge status="include" size="sm" />
        <StatusBadge status="include" size="md" />
        <StatusBadge status="include" size="lg" />
      </div>
    `,
  }),
}

export const DecisionTypes: Story = {
  render: () => ({
    components: { StatusBadge },
    template: `
      <div class="flex flex-wrap gap-2">
        <StatusBadge status="include" />
        <StatusBadge status="exclude" />
        <StatusBadge status="maybe" />
      </div>
    `,
  }),
}

export const ConflictStatuses: Story = {
  render: () => ({
    components: { StatusBadge },
    template: `
      <div class="flex flex-wrap gap-2">
        <StatusBadge status="PENDING" />
        <StatusBadge status="IN_DISCUSSION" />
        <StatusBadge status="RESOLVED" />
        <StatusBadge status="ESCALATED" />
      </div>
    `,
  }),
}

export const ProposalStatuses: Story = {
  render: () => ({
    components: { StatusBadge },
    template: `
      <div class="flex flex-wrap gap-2">
        <StatusBadge status="PROPOSED" />
        <StatusBadge status="ACCEPTED" />
        <StatusBadge status="IN_PROGRESS" />
        <StatusBadge status="COMPLETED" />
        <StatusBadge status="REJECTED" />
        <StatusBadge status="EXPIRED" />
      </div>
    `,
  }),
}

export const AllStatuses: Story = {
  render: () => ({
    components: { StatusBadge },
    template: `
      <div class="space-y-4">
        <div>
          <p class="text-sm font-medium mb-2">Decision Types</p>
          <div class="flex flex-wrap gap-2">
            <StatusBadge status="include" />
            <StatusBadge status="exclude" />
            <StatusBadge status="maybe" />
          </div>
        </div>
        <div>
          <p class="text-sm font-medium mb-2">General Statuses</p>
          <div class="flex flex-wrap gap-2">
            <StatusBadge status="pending" />
            <StatusBadge status="conflict" />
            <StatusBadge status="active" />
            <StatusBadge status="inactive" />
          </div>
        </div>
      </div>
    `,
  }),
}
