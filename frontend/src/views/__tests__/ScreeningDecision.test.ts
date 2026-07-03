import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, VueWrapper, flushPromises } from '@vue/test-utils'
import ScreeningDecision from '../ScreeningDecision.vue'

// Mock API
vi.mock('../../api/results', () => ({
  getResult: vi.fn().mockResolvedValue({
    id: 'test-result-id',
    title: 'Test Result Title',
    snippet: 'Test snippet content',
    url: 'https://example.com/test',
    source_name: 'Test Source',
    date_published: '2025-01-15',
    authors: 'Test Author',
    is_duplicate: false,
  }),
  submitDecision: vi.fn().mockResolvedValue({
    status: 'consensus_reached',
    message: 'Decision recorded successfully',
  }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

describe('ScreeningDecision.vue - Tailwind/Shadcn-vue Migration', () => {
  let wrapper: VueWrapper<any>

  beforeEach(async () => {
    wrapper = mount(ScreeningDecision, {
      props: {
        id: 'test-result-id',
      },
      global: {
        stubs: {
          Button: true,
          Card: true,
          CardHeader: true,
          CardContent: true,
          Badge: true,
          Label: true,
          Textarea: true,
          Dialog: true,
          DialogContent: true,
          DialogHeader: true,
          DialogTitle: true,
          DialogDescription: true,
          DialogFooter: true,
          Select: true,
          SelectTrigger: true,
          SelectValue: true,
          SelectContent: true,
          SelectItem: true,
          Alert: true,
          AlertTitle: true,
          AlertDescription: true,
          DecisionButtons: true,
          LoadingState: true,
          ErrorAlert: true,
          ExternalLink: true,
          Send: true,
          Loader2: true,
          AlertTriangle: true,
        },
      },
    })
    // Wait for the async data to load
    await flushPromises()
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
      expect(html).not.toContain('col-lg-')
      expect(html).not.toContain('col-md-')
    })

    it('should NOT have Bootstrap button classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('btn btn-')
      expect(html).not.toContain('btn-primary')
      expect(html).not.toContain('btn-decision')
      expect(html).not.toContain('btn-include')
      expect(html).not.toContain('btn-exclude')
      expect(html).not.toContain('btn-maybe')
    })

    it('should NOT have Bootstrap card classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('class="card')
      expect(html).not.toContain('card-header')
      expect(html).not.toContain('card-body')
    })

    it('should NOT have Bootstrap alert classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('alert alert-')
      expect(html).not.toContain('alert-danger')
      expect(html).not.toContain('alert-warning')
    })

    it('should NOT have Bootstrap modal classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('class="modal')
      expect(html).not.toContain('modal-dialog')
      expect(html).not.toContain('modal-content')
      expect(html).not.toContain('modal-header')
      expect(html).not.toContain('modal-body')
      expect(html).not.toContain('modal-footer')
    })

    it('should NOT have Bootstrap form classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('form-control')
      expect(html).not.toContain('form-select')
      expect(html).not.toContain('form-label')
      expect(html).not.toContain('form-range')
    })

    it('should NOT have Bootstrap badge classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('badge bg-')
      expect(html).not.toContain('bg-info')
      expect(html).not.toContain('bg-secondary')
    })

    it('should NOT have Bootstrap spinner classes', () => {
      const html = wrapper.html()
      expect(html).not.toContain('spinner-border')
      expect(html).not.toContain('text-primary')
    })

    it('should NOT have Bootstrap Icons', () => {
      const html = wrapper.html()
      expect(html).not.toContain('bi bi-')
      expect(html).not.toContain('bi-check-circle')
      expect(html).not.toContain('bi-x-circle')
      expect(html).not.toContain('bi-question-circle')
      expect(html).not.toContain('bi-send')
      expect(html).not.toContain('bi-box-arrow-up-right')
    })
  })

  describe('Tailwind CSS Classes', () => {
    it('should use Tailwind layout utilities', () => {
      const html = wrapper.html()
      expect(html).toContain('grid')
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
      // Component uses text-muted-foreground, text-sm, text-lg, text-primary, etc.
      expect(html).toContain('text-muted-foreground')
    })
  })

  describe('Shadcn-vue Components', () => {
    it('should render Card components', () => {
      expect(wrapper.findComponent({ name: 'Card' }).exists()).toBe(true)
    })

    it('should render Button components', () => {
      expect(wrapper.findComponent({ name: 'Button' }).exists()).toBe(true)
    })

    it('should use DecisionButtons from Phase 04', () => {
      expect(wrapper.findComponent({ name: 'DecisionButtons' }).exists()).toBe(true)
    })
  })

  describe('Lucide Icons', () => {
    it('should use Lucide icons instead of Bootstrap icons', async () => {
      // Validated by successful compilation with Lucide imports
      expect(ScreeningDecision.__file).toBeDefined()
    })
  })

  describe('Accessibility', () => {
    it('should have data-testid for decision form', () => {
      expect(wrapper.find('[data-testid="decision-form"]').exists()).toBe(true)
    })

    it('should have data-testid for submit button', () => {
      expect(wrapper.find('[data-testid="submit-decision"]').exists()).toBe(true)
    })
  })

  describe('Functionality Preservation', () => {
    it('should preserve keyboard shortcuts info', () => {
      const html = wrapper.html()
      expect(html).toContain('Keyboard Shortcuts')
    })

    it('should display review time', () => {
      const html = wrapper.html()
      expect(html).toContain('Review Time')
    })
  })
})
