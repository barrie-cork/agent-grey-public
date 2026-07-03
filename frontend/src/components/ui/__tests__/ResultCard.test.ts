import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { ResultCard } from '../result-card'

const mockResult = {
  id: 'test-1',
  title: 'Test Result Title',
  snippet: 'This is a test snippet for the result card.',
  url: 'https://example.com/test',
  metadata: {
    source: 'Test Source',
    date: '2024-01-15',
    author: 'Test Author'
  },
  decision: 'include' as const
}

describe('ResultCard', () => {
  it('renders result title', () => {
    const wrapper = mount(ResultCard, { props: { result: mockResult } })
    expect(wrapper.text()).toContain('Test Result Title')
  })

  it('renders result snippet', () => {
    const wrapper = mount(ResultCard, { props: { result: mockResult } })
    expect(wrapper.text()).toContain('This is a test snippet')
  })

  it('renders result URL as link', () => {
    const wrapper = mount(ResultCard, { props: { result: mockResult } })
    const link = wrapper.find('a[href="https://example.com/test"]')
    expect(link.exists()).toBe(true)
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
  })

  it('renders metadata when provided', () => {
    const wrapper = mount(ResultCard, { props: { result: mockResult } })
    expect(wrapper.text()).toContain('Test Source')
    expect(wrapper.text()).toContain('2024-01-15')
    expect(wrapper.text()).toContain('Test Author')
  })

  it('hides metadata when not provided', () => {
    const resultWithoutMeta = {
      ...mockResult,
      metadata: undefined
    }
    const wrapper = mount(ResultCard, { props: { result: resultWithoutMeta } })
    expect(wrapper.text()).not.toContain('Source:')
    expect(wrapper.text()).not.toContain('Date:')
    expect(wrapper.text()).not.toContain('Author:')
  })

  it('shows StatusBadge when decision is set and showDecision is true', () => {
    const wrapper = mount(ResultCard, {
      props: { result: mockResult, showDecision: true }
    })
    expect(wrapper.text()).toContain('Include')
  })

  it('hides StatusBadge when showDecision is false', () => {
    const wrapper = mount(ResultCard, {
      props: { result: mockResult, showDecision: false }
    })
    // Should not have the status badge text (capitalized)
    const badges = wrapper.findAll('[aria-label*="Status"]')
    expect(badges.length).toBe(0)
  })

  it('hides StatusBadge when no decision is set', () => {
    const resultWithoutDecision = { ...mockResult, decision: undefined }
    const wrapper = mount(ResultCard, {
      props: { result: resultWithoutDecision }
    })
    const badges = wrapper.findAll('[aria-label*="Status"]')
    expect(badges.length).toBe(0)
  })

  it('renders actions slot content', () => {
    const wrapper = mount(ResultCard, {
      props: { result: mockResult },
      slots: {
        actions: '<button>Custom Action</button>'
      }
    })
    expect(wrapper.text()).toContain('Custom Action')
  })

  it('has ExternalLink icon for URL', () => {
    const wrapper = mount(ResultCard, { props: { result: mockResult } })
    const link = wrapper.find('a[href="https://example.com/test"]')
    expect(link.find('svg').exists()).toBe(true)
  })

  it('applies hover shadow transition class', () => {
    const wrapper = mount(ResultCard, { props: { result: mockResult } })
    expect(wrapper.html()).toContain('hover:shadow-md')
  })
})
