import { Page } from '@playwright/test';

/**
 * Create test data for consensus discussion scenarios
 */

export interface ConflictData {
  conflictId: string;
  resultTitle: string;
  reviewer1Decision: 'INCLUDE' | 'EXCLUDE';
  reviewer2Decision: 'INCLUDE' | 'EXCLUDE';
}

export interface CommentData {
  content: string;
  parentId?: string;
}

export interface RevoteProposalData {
  rationale: string;
}

/**
 * Factory function to create a conflict via API
 */
export async function createConflict(
  page: Page,
  data: Partial<ConflictData> = {}
): Promise<ConflictData> {
  // Default conflict scenario
  const conflictData: ConflictData = {
    conflictId: data.conflictId || 'test-conflict-' + Date.now(),
    resultTitle: data.resultTitle || 'Test Grey Literature Result',
    reviewer1Decision: data.reviewer1Decision || 'INCLUDE',
    reviewer2Decision: data.reviewer2Decision || 'EXCLUDE',
  };

  // TODO: Implement actual API call to create conflict
  // For now, assuming conflict already exists in test database

  return conflictData;
}

/**
 * Factory function to create a comment
 */
export function createComment(content: string, parentId?: string): CommentData {
  return {
    content,
    parentId,
  };
}

/**
 * Factory function to create a re-vote proposal
 */
export function createRevoteProposal(rationale: string): RevoteProposalData {
  return {
    rationale,
  };
}

/**
 * Sample test data
 */
export const sampleConflicts = {
  simpleDisagreement: {
    conflictId: '550e8400-e29b-41d4-a716-446655440000',
    resultTitle: 'Clinical Guidelines for Systematic Review',
    reviewer1Decision: 'INCLUDE' as const,
    reviewer2Decision: 'EXCLUDE' as const,
  },

  maybeVsExclude: {
    conflictId: '550e8400-e29b-41d4-a716-446655440001',
    resultTitle: 'Policy Document on Healthcare Standards',
    reviewer1Decision: 'EXCLUDE' as const,
    reviewer2Decision: 'EXCLUDE' as const,
  },
};

export const sampleComments = {
  topLevel: createComment(
    'I think this document is highly relevant to our research question. ' +
    'It provides detailed guidelines on the intervention we are studying.'
  ),

  reply: createComment(
    'I disagree. While it mentions the intervention, it does not provide ' +
    'empirical data on outcomes, which is our inclusion criterion.',
    'parent-comment-uuid'
  ),

  withMarkdown: createComment(
    '## Key Points\n\n' +
    '- The document is from a reputable source\n' +
    '- It includes **primary research** data\n' +
    '- However, the `sample size` is too small (n=10)\n\n' +
    'Therefore, I propose we **exclude** this result.'
  ),
};

export const sampleRevoteProposal = createRevoteProposal(
  'After discussing the inclusion criteria, I believe we should re-vote. ' +
  'The document does contain relevant data, but it is from a preliminary study. ' +
  'Let us reconsider whether this meets our quality threshold.'
);
