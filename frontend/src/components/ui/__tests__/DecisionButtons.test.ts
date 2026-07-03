import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { DecisionButtons } from '../decision-buttons'

describe('DecisionButtons', () => {
  beforeEach(() => {
    // Clean up any previous event listeners
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders three buttons', () => {
    const wrapper = mount(DecisionButtons)
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(3)
    expect(wrapper.text()).toContain('Include')
    expect(wrapper.text()).toContain('Exclude')
    expect(wrapper.text()).toContain('Maybe')
  })

  it('emits decision event on Include button click', async () => {
    const wrapper = mount(DecisionButtons)
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(0)

    await buttons[0]!.trigger('click')
    expect(wrapper.emitted('decision')).toBeTruthy()
    expect(wrapper.emitted('decision')?.[0]).toEqual(['include'])
  })

  it('emits decision event on Exclude button click', async () => {
    const wrapper = mount(DecisionButtons)
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(1)

    await buttons[1]!.trigger('click')
    expect(wrapper.emitted('decision')?.[0]).toEqual(['exclude'])
  })

  it('emits decision event on Maybe button click', async () => {
    const wrapper = mount(DecisionButtons)
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(2)

    await buttons[2]!.trigger('click')
    expect(wrapper.emitted('decision')?.[0]).toEqual(['maybe'])
  })

  it('disables buttons when disabled prop is true', () => {
    const wrapper = mount(DecisionButtons, { props: { disabled: true } })
    wrapper.findAll('button').forEach(button => {
      expect(button.attributes('disabled')).toBeDefined()
    })
  })

  it('disables buttons when loading prop is true', () => {
    const wrapper = mount(DecisionButtons, { props: { loading: true } })
    wrapper.findAll('button').forEach(button => {
      expect(button.attributes('disabled')).toBeDefined()
    })
  })

  it('does not emit event when disabled', async () => {
    const wrapper = mount(DecisionButtons, { props: { disabled: true } })
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(0)

    await buttons[0]!.trigger('click')
    expect(wrapper.emitted('decision')).toBeFalsy()
  })

  it('highlights Include button when currentDecision is include', () => {
    const wrapper = mount(DecisionButtons, {
      props: { currentDecision: 'include' }
    })
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(0)
    const includeButton = buttons[0]!
    expect(includeButton.classes()).toContain('border-decision-include')
    expect(includeButton.classes()).toContain('bg-decision-include-light')
  })

  it('highlights Exclude button when currentDecision is exclude', () => {
    const wrapper = mount(DecisionButtons, {
      props: { currentDecision: 'exclude' }
    })
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(1)
    const excludeButton = buttons[1]!
    expect(excludeButton.classes()).toContain('border-decision-exclude')
    expect(excludeButton.classes()).toContain('bg-decision-exclude-light')
  })

  it('highlights Maybe button when currentDecision is maybe', () => {
    const wrapper = mount(DecisionButtons, {
      props: { currentDecision: 'maybe' }
    })
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(2)
    const maybeButton = buttons[2]!
    expect(maybeButton.classes()).toContain('border-decision-maybe')
    expect(maybeButton.classes()).toContain('bg-decision-maybe-light')
  })

  it('has accessible role="group" with aria-label', () => {
    const wrapper = mount(DecisionButtons)
    const group = wrapper.find('[role="group"]')
    expect(group.exists()).toBe(true)
    expect(group.attributes('aria-label')).toBe('Decision buttons')
  })

  it('shows keyboard shortcut hints', () => {
    const wrapper = mount(DecisionButtons)
    const kbds = wrapper.findAll('kbd')
    expect(kbds).toHaveLength(3)
    expect(kbds[0]!.text()).toBe('I')
    expect(kbds[1]!.text()).toBe('E')
    expect(kbds[2]!.text()).toBe('M')
  })
})
