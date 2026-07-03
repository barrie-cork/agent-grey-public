import type { Meta, StoryObj } from '@storybook/vue3-vite'
import WorkQueue from './WorkQueue.vue'

const meta: Meta<typeof WorkQueue> = {
  title: 'Views/WorkQueue',
  component: WorkQueue,
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component: 'Work queue page for claiming and reviewing search results.',
      },
    },
  },
  decorators: [
    (story) => ({
      components: { story },
      template: '<div class="min-h-screen bg-background"><story /></div>',
    }),
  ],
}

export default meta
type Story = StoryObj<typeof meta>

// Static mockup of the WorkQueue layout
export const LayoutMockup: Story = {
  render: () => ({
    template: `
      <div class="w-full px-6 py-4">
        <!-- Header -->
        <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground mb-2">Work Queue</h1>
            <p class="text-muted-foreground">
              Claim and screen results for your research review
            </p>
          </div>
          <div class="mt-4 md:mt-0">
            <button class="inline-flex items-center justify-center rounded-md text-sm font-medium bg-primary text-primary-foreground h-10 px-4 py-2">
              <svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Claim Next Result
            </button>
          </div>
        </div>

        <!-- Progress Widget -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div class="bg-muted/50 rounded-lg border p-4">
            <p class="text-sm text-muted-foreground mb-1">Pending</p>
            <p class="text-2xl font-bold text-foreground">24</p>
          </div>
          <div class="bg-muted/50 rounded-lg border p-4">
            <p class="text-sm text-muted-foreground mb-1">My Claims</p>
            <p class="text-2xl font-bold text-foreground">3</p>
          </div>
          <div class="bg-muted/50 rounded-lg border p-4">
            <p class="text-sm text-muted-foreground mb-1">Completed</p>
            <p class="text-2xl font-bold text-foreground">47</p>
          </div>
          <div class="bg-[color:var(--color-warning-light)] border-[color:var(--color-warning)] rounded-lg border p-4">
            <p class="text-sm text-muted-foreground mb-1">Conflicts</p>
            <p class="text-2xl font-bold text-[color:var(--color-warning-dark)]">2</p>
          </div>
        </div>

        <!-- Filters -->
        <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-4">
          <div class="inline-flex rounded-lg border border-input">
            <button class="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-l-lg">
              Pending (24)
            </button>
            <button class="px-4 py-2 text-sm font-medium hover:bg-accent border-x border-input">
              My Claims (3)
            </button>
            <button class="px-4 py-2 text-sm font-medium hover:bg-accent rounded-r-lg">
              Conflicts (2)
            </button>
          </div>
          <div class="mt-4 md:mt-0">
            <button class="inline-flex items-center px-4 py-2 border rounded-md text-sm font-medium hover:bg-accent">
              <svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </button>
          </div>
        </div>

        <!-- Results Table -->
        <div class="rounded-lg border bg-card">
          <table class="w-full">
            <thead class="border-b bg-muted/50">
              <tr>
                <th class="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Title</th>
                <th class="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Source</th>
                <th class="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Status</th>
                <th class="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr class="border-b">
                <td class="px-4 py-3">
                  <a href="#" class="text-primary hover:underline font-medium">COVID-19 Vaccination Guidelines</a>
                  <p class="text-sm text-muted-foreground truncate max-w-md">This document provides comprehensive guidance on vaccination...</p>
                </td>
                <td class="px-4 py-3 text-sm">NHS England</td>
                <td class="px-4 py-3">
                  <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-[color:var(--color-info-light)] text-[color:var(--color-info-dark)]">
                    Pending
                  </span>
                </td>
                <td class="px-4 py-3">
                  <button class="text-sm text-primary hover:underline">Claim</button>
                </td>
              </tr>
              <tr class="border-b">
                <td class="px-4 py-3">
                  <a href="#" class="text-primary hover:underline font-medium">Mental Health Policy Framework</a>
                  <p class="text-sm text-muted-foreground truncate max-w-md">A comprehensive framework for mental health services...</p>
                </td>
                <td class="px-4 py-3 text-sm">WHO</td>
                <td class="px-4 py-3">
                  <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-[color:var(--color-success-light)] text-[color:var(--color-success-dark)]">
                    Claimed
                  </span>
                </td>
                <td class="px-4 py-3">
                  <button class="text-sm text-primary hover:underline">Review</button>
                </td>
              </tr>
              <tr>
                <td class="px-4 py-3">
                  <a href="#" class="text-primary hover:underline font-medium">Healthcare Access Report 2024</a>
                  <p class="text-sm text-muted-foreground truncate max-w-md">Annual report on healthcare access and outcomes...</p>
                </td>
                <td class="px-4 py-3 text-sm">CDC</td>
                <td class="px-4 py-3">
                  <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-[color:var(--color-warning-light)] text-[color:var(--color-warning-dark)]">
                    Conflict
                  </span>
                </td>
                <td class="px-4 py-3">
                  <button class="text-sm text-primary hover:underline">Resolve</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    `,
  }),
}

export const EmptyState: Story = {
  render: () => ({
    template: `
      <div class="w-full px-6 py-4">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground mb-2">Work Queue</h1>
            <p class="text-muted-foreground">
              Claim and screen results for your research review
            </p>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div class="bg-muted/50 rounded-lg border p-4">
            <p class="text-sm text-muted-foreground mb-1">Pending</p>
            <p class="text-2xl font-bold text-foreground">0</p>
          </div>
          <div class="bg-muted/50 rounded-lg border p-4">
            <p class="text-sm text-muted-foreground mb-1">My Claims</p>
            <p class="text-2xl font-bold text-foreground">0</p>
          </div>
          <div class="bg-muted/50 rounded-lg border p-4">
            <p class="text-sm text-muted-foreground mb-1">Completed</p>
            <p class="text-2xl font-bold text-foreground">0</p>
          </div>
          <div class="bg-muted/50 rounded-lg border p-4">
            <p class="text-sm text-muted-foreground mb-1">Conflicts</p>
            <p class="text-2xl font-bold text-foreground">0</p>
          </div>
        </div>

        <div class="rounded-lg border bg-card p-12 text-center">
          <svg class="mx-auto h-12 w-12 text-muted-foreground mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
          <h3 class="text-lg font-semibold text-foreground mb-2">All caught up!</h3>
          <p class="text-muted-foreground">No results are currently pending review.</p>
        </div>
      </div>
    `,
  }),
}

export const Loading: Story = {
  render: () => ({
    template: `
      <div class="w-full px-6 py-4">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground mb-2">Work Queue</h1>
            <p class="text-muted-foreground">
              Claim and screen results for your research review
            </p>
          </div>
        </div>

        <div class="flex items-center justify-center py-12">
          <svg class="animate-spin h-8 w-8 text-primary mr-3" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span class="text-muted-foreground">Loading work queue...</span>
        </div>
      </div>
    `,
  }),
}
