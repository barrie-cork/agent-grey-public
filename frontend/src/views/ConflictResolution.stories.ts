import type { Meta, StoryObj } from '@storybook/vue3-vite'
import ConflictResolution from './ConflictResolution.vue'

const meta: Meta<typeof ConflictResolution> = {
  title: 'Views/ConflictResolution',
  component: ConflictResolution,
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component: 'Conflict resolution page for handling reviewer disagreements.',
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

export const LayoutMockup: Story = {
  render: () => ({
    template: `
      <div class="w-full px-6 py-4">
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Conflict Details -->
          <div class="lg:col-span-2">
            <!-- Header -->
            <div class="bg-card rounded-lg border shadow-sm mb-4">
              <div class="p-6 flex items-center justify-between border-b">
                <h4 class="text-lg font-semibold">Conflict Resolution</h4>
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-[color:var(--color-warning-light)] text-[color:var(--color-warning-dark)]">
                  Pending
                </span>
              </div>
              <div class="p-6">
                <div class="bg-[color:var(--color-warning-light)] border border-[color:var(--color-warning)] rounded-md p-4 mb-4 flex items-start gap-3">
                  <svg class="h-6 w-6 text-[color:var(--color-warning-dark)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <div>
                    <p class="font-semibold">Conflict Type: Include vs. Exclude</p>
                    <p class="text-sm text-muted-foreground">Detected: 1 Jan 2025</p>
                  </div>
                </div>
                
                <!-- Result Preview -->
                <div class="p-4 bg-muted rounded-lg border-l-4 border-[color:var(--color-warning)]">
                  <h5 class="font-semibold mb-3">Result Details</h5>
                  <div class="mb-2">
                    <span class="font-medium">Title:</span> COVID-19 Vaccination Guidelines for Immunocompromised Patients
                  </div>
                  <div class="mb-2">
                    <span class="font-medium">Snippet:</span> This document provides comprehensive guidance on COVID-19 vaccination strategies...
                  </div>
                  <div>
                    <span class="font-medium">URL:</span>
                    <a href="#" class="ml-2 text-primary hover:underline">https://example.gov/guidelines</a>
                  </div>
                </div>
              </div>
            </div>

            <!-- Reviewer Decisions -->
            <div class="bg-card rounded-lg border shadow-sm mb-4">
              <div class="p-6 border-b">
                <h5 class="text-lg font-semibold">Reviewer Decisions</h5>
              </div>
              <div class="p-6 space-y-4">
                <!-- Reviewer 1 -->
                <div class="bg-white rounded-lg border-l-4 border-[color:var(--color-success)] p-4">
                  <div class="flex items-center justify-between mb-2">
                    <h6 class="font-semibold">Dr. Jane Smith</h6>
                    <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-[color:var(--color-success-light)] text-[color:var(--color-success-dark)]">
                      Include
                    </span>
                  </div>
                  <p class="text-sm text-muted-foreground mb-2">
                    <strong>Notes:</strong> This document is highly relevant to our research question.
                  </p>
                  <p class="text-xs text-muted-foreground">Confidence: High</p>
                </div>
                
                <!-- Reviewer 2 -->
                <div class="bg-white rounded-lg border-l-4 border-destructive p-4">
                  <div class="flex items-center justify-between mb-2">
                    <h6 class="font-semibold">Dr. Robert Johnson</h6>
                    <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-destructive/10 text-destructive">
                      Exclude
                    </span>
                  </div>
                  <p class="text-sm text-muted-foreground mb-2">
                    <strong>Reason:</strong> Not relevant to research scope
                  </p>
                  <p class="text-sm text-muted-foreground mb-2">
                    <strong>Notes:</strong> The document focuses on a different population.
                  </p>
                  <p class="text-xs text-muted-foreground">Confidence: Medium</p>
                </div>
              </div>
            </div>

            <!-- Discussion Thread -->
            <div class="bg-card rounded-lg border shadow-sm">
              <div class="p-6 border-b">
                <h5 class="text-lg font-semibold">Discussion Thread (2 comments)</h5>
              </div>
              <div class="p-6">
                <div class="space-y-4">
                  <div class="bg-white rounded-lg border p-4">
                    <div class="flex items-start gap-3">
                      <div class="h-10 w-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-semibold text-sm">JS</div>
                      <div class="flex-1">
                        <div class="flex items-center justify-between mb-1">
                          <p class="font-semibold text-sm">Jane Smith</p>
                          <span class="text-xs text-muted-foreground">5 minutes ago</span>
                        </div>
                        <p class="text-sm">I believe this should be included because it directly addresses our research question about vaccination strategies.</p>
                      </div>
                    </div>
                  </div>
                  <div class="bg-white rounded-lg border p-4">
                    <div class="flex items-start gap-3">
                      <div class="h-10 w-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-semibold text-sm">RJ</div>
                      <div class="flex-1">
                        <div class="flex items-center justify-between mb-1">
                          <p class="font-semibold text-sm">Robert Johnson</p>
                          <span class="text-xs text-muted-foreground">2 minutes ago</span>
                        </div>
                        <p class="text-sm">The population in this study is quite different from our target. I'd suggest we discuss this further.</p>
                      </div>
                    </div>
                  </div>
                </div>
                
                <!-- Comment Form -->
                <div class="mt-6 pt-6 border-t">
                  <label class="block text-sm font-semibold mb-2">Add your comment</label>
                  <textarea class="w-full border rounded-md p-3 text-sm" rows="3" placeholder="Write your comment here... (Markdown supported)"></textarea>
                  <div class="flex justify-end mt-2">
                    <button class="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium">
                      Post Comment
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Resolution Panel (Right Column) -->
          <div class="lg:col-span-1">
            <div class="bg-card rounded-lg border shadow-sm sticky top-4">
              <div class="p-6 border-b">
                <h5 class="text-lg font-semibold">Resolution Actions</h5>
              </div>
              <div class="p-6 space-y-4">
                <button class="w-full bg-[color:var(--color-success)] text-white rounded-md px-4 py-3 text-sm font-medium hover:bg-[color:var(--color-success-dark)]">
                  Resolve as Include
                </button>
                <button class="w-full bg-destructive text-destructive-foreground rounded-md px-4 py-3 text-sm font-medium hover:bg-destructive/90">
                  Resolve as Exclude
                </button>
                <button class="w-full border border-[color:var(--color-warning)] text-[color:var(--color-warning-dark)] bg-[color:var(--color-warning-light)] rounded-md px-4 py-3 text-sm font-medium">
                  Propose Re-Vote
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `,
  }),
}

export const Loading: Story = {
  render: () => ({
    template: `
      <div class="w-full px-6 py-4">
        <div class="flex items-center justify-center py-12">
          <svg class="animate-spin h-8 w-8 text-primary mr-3" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span class="text-muted-foreground">Loading conflict details...</span>
        </div>
      </div>
    `,
  }),
}

export const Resolved: Story = {
  render: () => ({
    template: `
      <div class="w-full px-6 py-4">
        <div class="max-w-2xl mx-auto">
          <div class="bg-card rounded-lg border shadow-sm">
            <div class="p-6 flex items-center justify-between border-b">
              <h4 class="text-lg font-semibold">Conflict Resolution</h4>
              <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-[color:var(--color-success-light)] text-[color:var(--color-success-dark)]">
                Resolved
              </span>
            </div>
            <div class="p-6">
              <div class="bg-[color:var(--color-success-light)] border border-[color:var(--color-success)] rounded-md p-4 flex items-start gap-3">
                <svg class="h-6 w-6 text-[color:var(--color-success-dark)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <p class="font-semibold">Conflict Resolved</p>
                  <p class="text-sm text-muted-foreground">
                    Final decision: <strong>Include</strong><br />
                    Resolved by: Dr. Sarah Williams on 1 Jan 2025
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `,
  }),
}
