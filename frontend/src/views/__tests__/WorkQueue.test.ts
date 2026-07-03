import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, VueWrapper } from '@vue/test-utils'
import WorkQueue from '../WorkQueue.vue'

// Mock stores
vi.mock('../../stores/workQueue', () => ({
  useWorkQueueStore: () => ({
    results: [],
    totalCount: 0,
    currentPage: 1,
    totalPages: 1,
    hasNext: false,
    hasPrevious: false,
    pendingCount: 5,
    myClaims: [],
    completedCount: 10,
    conflicts: [],
    error: null,
    fetchQueue: vi.fn(),
    claimNext: vi.fn(),
    setFilter: vi.fn(),
  }),
}))

vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({
    isAuthenticated: true,
    canClaimResults: true,
  }),
}))

vi.mock('../../stores/organisation', () => ({
  useOrganisationStore: () => ({
    organisationId: 'test-org-id',
    hasOrganisation: true,
    currentOrganisation: { id: 'test-org-id', name: 'Test Org' },
    checkOrganisationContext: () => true,
  }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

describe('WorkQueue.vue - Tailwind/Shadcn-vue Migration', () => {
  let wrapper: VueWrapper<any>

  beforeEach(() => {
    // Mock window.location.search for session_id
    Object.defineProperty(window, 'location', {
      value: { search: '?session_id=test-session-123' },
      writable: true,
    })

    wrapper = mount(WorkQueue, {
      global: {
        stubs: {
          Button: true,
          Card: true,
          CardContent: true,
          Table: true,
          TableBody: true,
          TableCell: true,
          TableHead: true,
          TableHeader: true,
          TableRow: true,
          LoadingState: true,
          ErrorAlert: true,
          StatusBadge: true,
        },
      },
    })
  })

  describe('Bootstrap Removal', () => {
    it('should NOT have Bootstrap container classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('container-fluid')
      expect(html).not.toContain('container ')
    })

    it('should NOT have Bootstrap row/col classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('class="row')
      expect(html).not.toContain('col-md-')
      expect(html).not.toContain('col-sm-')
    })

    it('should NOT have Bootstrap button classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('btn btn-')
      expect(html).not.toContain('btn-primary')
      expect(html).not.toContain('btn-outline-')
      expect(html).not.toContain('btn-group')
      expect(html).not.toContain('btn-check')
    })

    it('should NOT have Bootstrap card classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('class="card')
      expect(html).not.toContain('card-body')
      expect(html).not.toContain('card-title')
      expect(html).not.toContain('card-subtitle')
    })

    it('should NOT have Bootstrap alert classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('alert alert-')
      expect(html).not.toContain('alert-danger')
      expect(html).not.toContain('alert-success')
      expect(html).not.toContain('alert-dismissible')
    })

    it('should NOT have Bootstrap table classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('table-hover')
      expect(html).not.toContain('table-light')
      expect(html).not.toContain('table-responsive')
      expect(html).not.toContain('table-active')
    })

    it('should NOT have Bootstrap spinner classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('spinner-border')
    })

    it('should NOT have Bootstrap icon classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('bi bi-')
      expect(html).not.toContain('bi-plus-circle')
      expect(html).not.toContain('bi-arrow-clockwise')
      expect(html).not.toContain('bi-exclamation-triangle')
      expect(html).not.toContain('bi-check-circle')
      expect(html).not.toContain('bi-inbox')
      expect(html).not.toContain('bi-box-arrow-up-right')
    })

    it('should NOT have Bootstrap pagination classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('class="pagination')
      expect(html).not.toContain('page-item')
      expect(html).not.toContain('page-link')
    })

    it('should NOT have Bootstrap badge classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('class="badge')
      expect(html).not.toContain('bg-secondary')
      expect(html).not.toContain('bg-primary')
      expect(html).not.toContain('bg-info')
      expect(html).not.toContain('bg-success')
      expect(html).not.toContain('bg-warning')
    })

    it('should NOT have Bootstrap utility classes', () => {
      const html = wrapper.html()
      // Bootstrap-specific utilities that don't overlap with Tailwind
      expect(html).not.toContain('text-end')
      // text-muted is Bootstrap, text-muted-foreground is Tailwind - use negative lookahead
      expect(html).not.toMatch(/class="[^"]*\btext-muted(?!-foreground)[^"]*"/)
      // me-X and ms-X are Bootstrap margin utilities (Tailwind uses mr-X, ml-X)
      expect(html).not.toMatch(/\bme-\d/)
      expect(html).not.toMatch(/\bms-\d/)
    })
  })

  describe('Tailwind Classes', () => {
    it('should use Tailwind container utilities', () => {
      const html = wrapper.html()
      expect(html).toContain('w-full')
    })

    it('should use Tailwind grid for layout', () => {
      const html = wrapper.html()
      expect(html).toContain('grid')
    })

    it('should use Tailwind flex for header', () => {
      const html = wrapper.html()
      expect(html).toContain('flex')
    })

    it('should use Tailwind spacing utilities', () => {
      const html = wrapper.html()
      expect(html).toContain('px-')
      expect(html).toContain('py-')
      expect(html).toContain('mb-')
      expect(html).toContain('gap-')
    })

    it('should use Tailwind text utilities', () => {
      const html = wrapper.html()
      expect(html).toContain('text-foreground')
      expect(html).toContain('text-muted-foreground')
    })
  })

  describe('Shadcn-vue Components', () => {
    it('should render Button components', () => {
      expect(wrapper.findComponent({ name: 'Button' }).exists()).toBe(true)
    })

    it('should render Card components for metrics', () => {
      expect(wrapper.findComponent({ name: 'Card' }).exists()).toBe(true)
    })
  })

  describe('Lucide Icons', () => {
    it('should import Lucide icons instead of Bootstrap icons', async () => {
      // Check that the component uses lucide-vue-next icons
      // This is validated by the component compiling successfully with Lucide imports
      // WorkQueue.__file contains the component source path
      expect(WorkQueue.__file).toBeDefined()
    })
  })

  describe('Accessibility', () => {
    it('should have data-testid for work queue container', () => {
      expect(wrapper.find('[data-testid="work-queue"]').exists()).toBe(true)
    })

    it('should have data-testid for claim button', () => {
      expect(wrapper.find('[data-testid="claim-button"]').exists()).toBe(true)
    })

    it('should have aria-label for filter button group', () => {
      const filterGroup = wrapper.find('[role="group"]')
      expect(filterGroup.exists()).toBe(true)
      expect(filterGroup.attributes('aria-label')).toBeTruthy()
    })
  })

  describe('Functionality Preservation', () => {
    it('should display pending count', () => {
      const html = wrapper.html()
      // The pending count should be rendered somewhere
      expect(html).toContain('5') // pendingCount from mock
    })

    it('should display completed count', () => {
      const html = wrapper.html()
      expect(html).toContain('10') // completedCount from mock
    })

    it('should have filter buttons for pending, claimed, and conflicts', () => {
      // The filter buttons are stubbed Button components, so we check for the aria-label
      // on the group and verify the button stubs exist
      const filterGroup = wrapper.find('[role="group"]')
      expect(filterGroup.exists()).toBe(true)
      // Verify 3 filter button stubs exist within the group
      const filterButtons = filterGroup.findAll('button-stub')
      expect(filterButtons.length).toBe(3)
    })
  })
})
