import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import ScreeningDecision from './ScreeningDecision.vue'

// Mock result data
const mockResult = {
  id: '123',
  title: 'COVID-19 Vaccination Guidelines for Immunocompromised Patients: A Comprehensive Review',
  url: 'https://example.gov/guidelines/covid-vaccination-immunocompromised',
  snippet: 'This document provides comprehensive guidance on COVID-19 vaccination strategies for patients with compromised immune systems, including timing, dosage recommendations, and monitoring protocols based on the latest clinical evidence and regulatory guidelines.',
  source_name: 'NHS England',
  result_type: 'Clinical Guideline',
  authors: 'Dr. Jane Smith, Dr. Robert Johnson, Prof. Sarah Williams',
  date_published: '2024-03-15',
  is_duplicate: false,
}

const mockResultDuplicate = {
  ...mockResult,
  id: '124',
  is_duplicate: true,
}

const meta: Meta<typeof ScreeningDecision> = {
  title: 'Views/ScreeningDecision',
  component: ScreeningDecision,
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component: 'Full-page screening decision view for reviewing search results.',
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

// We can't fully mock the API in Storybook easily, so we'll show the loading state
// and document the component structure
export const Loading: Story = {
  args: {
    id: '123',
  },
  parameters: {
    docs: {
      description: {
        story: 'Loading state shown while fetching result data.',
      },
    },
  },
}

// For a more complete demo, we'd need to mock the API
// This shows the component structure
export const ComponentStructure: Story = {
  render: () => ({
    setup() {
      const loading = ref(false)
      const error = ref(null)
      const result = ref(mockResult)
      const selectedDecision = ref('')
      const confidenceLevel = ref(2)
      const elapsedSeconds = ref(45)
      
      const formattedTime = () => {
        const minutes = Math.floor(elapsedSeconds.value / 60)
        const seconds = elapsedSeconds.value % 60
        return `${minutes}:${seconds.toString().padStart(2, '0')}`
      }
      
      return { loading, error, result, selectedDecision, confidenceLevel, formattedTime }
    },
    template: `
      <div class="w-full px-6 py-4">
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Result Display -->
          <div class="lg:col-span-2">
            <div class="bg-card rounded-lg border shadow-sm p-6 mb-4">
              <div class="flex items-center justify-between mb-4">
                <h5 class="text-lg font-semibold">Review Result</h5>
                <span class="inline-flex items-center rounded-md bg-secondary px-2 py-1 text-xs font-medium">SCREENING</span>
              </div>
              
              <h4 class="mb-3 text-xl font-semibold">{{ result.title }}</h4>
              
              <div class="mb-3">
                <h6 class="text-muted-foreground text-sm font-medium">Snippet</h6>
                <p class="text-sm">{{ result.snippet }}</p>
              </div>
              
              <div class="mb-3">
                <h6 class="text-muted-foreground text-sm font-medium">URL</h6>
                <a :href="result.url" class="text-primary hover:underline text-sm">{{ result.url }}</a>
              </div>
              
              <div class="grid grid-cols-2 gap-4 mt-4">
                <div>
                  <h6 class="text-muted-foreground text-sm font-medium">Source</h6>
                  <p>{{ result.source_name }}</p>
                </div>
                <div>
                  <h6 class="text-muted-foreground text-sm font-medium">Published</h6>
                  <p>{{ result.date_published }}</p>
                </div>
              </div>
              
              <div class="mt-4 p-3 bg-muted rounded-lg">
                <div class="flex justify-between items-center">
                  <span class="font-semibold">Review Time:</span>
                  <span class="border rounded px-2 py-1 text-sm">{{ formattedTime() }}</span>
                </div>
              </div>
            </div>
          </div>
          
          <!-- Decision Form -->
          <div class="lg:col-span-1">
            <div class="bg-card rounded-lg border shadow-sm p-6 sticky top-4">
              <h5 class="text-lg font-semibold mb-4">Make Decision</h5>
              
              <div class="mb-4">
                <label class="font-semibold mb-2 block">Decision</label>
                <div class="flex gap-2">
                  <button class="flex-1 px-4 py-2 border rounded-md text-sm font-medium hover:bg-accent">Include</button>
                  <button class="flex-1 px-4 py-2 border rounded-md text-sm font-medium hover:bg-accent">Exclude</button>
                  <button class="flex-1 px-4 py-2 border rounded-md text-sm font-medium hover:bg-accent">Maybe</button>
                </div>
              </div>
              
              <div class="mb-4">
                <label class="font-semibold mb-2 block">Confidence Level: <span class="text-[color:var(--color-info)]">Medium</span></label>
                <input type="range" class="w-full" min="1" max="3" :value="confidenceLevel" />
                <div class="flex justify-between text-sm text-muted-foreground mt-1">
                  <span>Low</span>
                  <span>Medium</span>
                  <span>High</span>
                </div>
              </div>
              
              <div class="mb-4">
                <label class="font-semibold mb-2 block">Notes <span class="text-muted-foreground">(Optional)</span></label>
                <textarea class="w-full border rounded-md p-2 text-sm" rows="4" placeholder="Add any relevant notes..."></textarea>
              </div>
              
              <button class="w-full bg-primary text-primary-foreground rounded-md px-4 py-2 font-medium">
                Submit Decision
              </button>
              
              <div class="mt-3 p-2 bg-muted rounded-lg text-sm text-muted-foreground">
                <strong>Keyboard Shortcuts:</strong><br />
                <kbd class="px-1.5 py-0.5 text-xs border rounded bg-background">I</kbd> Include
                <kbd class="px-1.5 py-0.5 text-xs border rounded bg-background ml-2">M</kbd> Maybe
                <kbd class="px-1.5 py-0.5 text-xs border rounded bg-background ml-2">E</kbd> Exclude
              </div>
            </div>
          </div>
        </div>
      </div>
    `,
  }),
}

export const WithDuplicateWarning: Story = {
  render: () => ({
    setup() {
      return { result: mockResultDuplicate }
    },
    template: `
      <div class="w-full px-6 py-4">
        <div class="max-w-4xl">
          <div class="bg-card rounded-lg border shadow-sm p-6">
            <h4 class="mb-3 text-xl font-semibold">{{ result.title }}</h4>
            
            <div class="bg-[color:var(--color-warning-light)] border border-[color:var(--color-warning)] rounded-md p-4 flex items-start gap-2">
              <svg class="h-5 w-5 text-[color:var(--color-warning-dark)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <strong>Duplicate:</strong> This result may be a duplicate of another entry.
              </div>
            </div>
          </div>
        </div>
      </div>
    `,
  }),
}
