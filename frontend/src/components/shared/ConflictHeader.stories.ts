import type { Meta, StoryObj } from '@storybook/vue3-vite'
import ConflictHeader from './ConflictHeader.vue'

const mockResult = {
  id: '1',
  title: 'COVID-19 Vaccination Guidelines for Immunocompromised Patients',
  url: 'https://example.gov/guidelines/covid-vaccination',
  snippet: 'This document provides comprehensive guidance on COVID-19 vaccination strategies for patients with compromised immune systems, including timing, dosage recommendations, and monitoring protocols.',
  source_name: 'NHS England',
  result_type: 'Clinical Guideline',
  authors: 'Dr. Jane Smith, Dr. Robert Johnson',
  date_published: '2024-03-15',
}

const meta: Meta<typeof ConflictHeader> = {
  title: 'Shared/ConflictHeader',
  component: ConflictHeader,
  tags: ['autodocs'],
  argTypes: {
    conflictType: {
      control: 'select',
      options: ['INCLUDE_EXCLUDE', 'INCLUDE_MAYBE', 'EXCLUDE_MAYBE', 'MULTIPLE_DISAGREEMENT'],
    },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    result: mockResult,
    conflictType: 'INCLUDE_EXCLUDE',
    detectedAt: new Date().toISOString(),
  },
}

export const IncludeVsMaybe: Story = {
  args: {
    result: mockResult,
    conflictType: 'INCLUDE_MAYBE',
    detectedAt: new Date().toISOString(),
  },
}

export const ExcludeVsMaybe: Story = {
  args: {
    result: mockResult,
    conflictType: 'EXCLUDE_MAYBE',
    detectedAt: new Date().toISOString(),
  },
}

export const MultipleDisagreement: Story = {
  args: {
    result: mockResult,
    conflictType: 'MULTIPLE_DISAGREEMENT',
    detectedAt: new Date().toISOString(),
  },
}

export const MinimalResult: Story = {
  args: {
    result: {
      id: '2',
      title: 'Policy Document on Healthcare Access',
      url: 'https://example.org/policy',
      snippet: null,
      source_name: null,
      result_type: null,
      authors: null,
      date_published: null,
    },
    conflictType: 'INCLUDE_EXCLUDE',
  },
}
