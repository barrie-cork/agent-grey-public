import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { StatusBadge } from '../status-badge'

describe('StatusBadge', () => {
  it('renders with default props', () => {
    const wrapper = mount(StatusBadge)
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('Pending')
  })

  it('renders all status variants', () => {
    const statuses = ['conflict', 'proposal', 'decision', 'include', 'exclude', 'maybe', 'pending', 'active', 'inactive'] as const

    statuses.forEach(status => {
      const wrapper = mount(StatusBadge, { props: { status } })
      expect(wrapper.exists()).toBe(true)
    })
  })

  it('renders with custom content via slot', () => {
    const wrapper = mount(StatusBadge, {
      props: { status: 'include' },
      slots: { default: 'Custom Label' }
    })
    expect(wrapper.text()).toContain('Custom Label')
  })

  it('shows icon by default', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'include' } })
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('hides icon when showIcon is false', () => {
    const wrapper = mount(StatusBadge, {
      props: { status: 'include', showIcon: false }
    })
    expect(wrapper.find('svg').exists()).toBe(false)
  })

  it('applies correct size classes for sm', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'pending', size: 'sm' } })
    expect(wrapper.html()).toContain('text-xs')
  })

  it('applies correct size classes for md', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'pending', size: 'md' } })
    expect(wrapper.html()).toContain('text-sm')
  })

  it('applies correct size classes for lg', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'pending', size: 'lg' } })
    expect(wrapper.html()).toContain('text-base')
  })

  it('applies include variant classes (green)', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'include' } })
    expect(wrapper.html()).toContain('--color-decision-include')
  })

  it('applies exclude variant classes (red)', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'exclude' } })
    expect(wrapper.html()).toContain('--color-decision-exclude')
  })

  it('applies conflict variant classes (amber)', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'conflict' } })
    expect(wrapper.html()).toContain('--color-status-escalated')
  })

  it('has accessible aria-label', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'include' } })
    expect(wrapper.attributes('aria-label')).toContain('Include')
  })

  // Backward compatibility with old shared StatusBadge uppercase values
  it('supports uppercase INCLUDE status', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'INCLUDE' } })
    expect(wrapper.text()).toContain('Include')
    expect(wrapper.html()).toContain('--color-decision-include')
  })

  it('supports uppercase EXCLUDE status', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'EXCLUDE' } })
    expect(wrapper.text()).toContain('Exclude')
    expect(wrapper.html()).toContain('--color-decision-exclude')
  })

  it('supports uppercase PENDING status', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'PENDING' } })
    expect(wrapper.text()).toContain('Pending')
    expect(wrapper.html()).toContain('--color-status-pending')
  })

  it('supports uppercase IN_DISCUSSION status', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'IN_DISCUSSION' } })
    expect(wrapper.text()).toContain('In Discussion')
    expect(wrapper.html()).toContain('--color-status-discussion')
  })

  it('supports old size prop values (small, medium, large)', () => {
    const wrapperSmall = mount(StatusBadge, { props: { status: 'pending', size: 'small' } })
    expect(wrapperSmall.html()).toContain('text-xs')

    const wrapperMedium = mount(StatusBadge, { props: { status: 'pending', size: 'medium' } })
    expect(wrapperMedium.html()).toContain('text-sm')

    const wrapperLarge = mount(StatusBadge, { props: { status: 'pending', size: 'large' } })
    expect(wrapperLarge.html()).toContain('text-base')
  })
})
