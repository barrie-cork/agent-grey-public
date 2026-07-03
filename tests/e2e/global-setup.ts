/**
 * Playwright Global Setup
 *
 * Runs once before all E2E tests to set up the test environment:
 * 1. Creates test users via create_e2e_users management command
 * 2. Seeds sessions at key workflow states via setup_e2e_session
 *
 * Session IDs are written to a JSON file for test fixtures to consume.
 *
 * Created for: GitHub Issue #33 - E2E Authentication Failure Resolution
 * Extended for: Comprehensive E2E Testing Plan (Phase 1, Task 5)
 */

import { FullConfig } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

/** Path to the seeded session IDs file (consumed by test fixtures) */
export const SEEDED_SESSIONS_PATH = path.join(__dirname, '.seeded-sessions.json');

/** Session states seeded during global setup */
export interface SeededSessions {
  /** Session in draft state (WF1) */
  draft: string;
  /** Session in defining_search state (WF1) */
  definingSearch: string;
  /** Session in ready_for_review state (WF1, single reviewer) */
  readyForReviewWf1: string;
  /** Session in ready_for_review state (WF2, dual screening) */
  readyForReviewWf2: string;
  /** Session in under_review state (WF2, decisions made, conflicts exist) */
  underReviewWf2: string;
  /** Session in completed state (WF1) */
  completedWf1: string;
  /** Session in completed state (WF2, conflicts resolved) */
  completedWf2: string;
}

/**
 * Run a management command and extract SESSION_ID from output.
 */
function runSetupCommand(args: string): string {
  const output = execSync(
    `docker compose exec -T web python manage.py setup_e2e_session ${args}`,
    { timeout: 60000, encoding: 'utf-8' }
  );

  const match = output.match(/SESSION_ID=([a-f0-9-]+)/);
  if (!match) {
    throw new Error(`Could not extract SESSION_ID from output:\n${output}`);
  }
  return match[1];
}

async function globalSetup(config: FullConfig) {
  console.log('\n=== E2E Global Setup ===');
  console.log('Setting up test data...\n');

  try {
    // Step 1: Create test users and organisation
    console.log('Step 1: Creating test users...');
    execSync(
      'docker compose exec -T web python manage.py create_e2e_users',
      { stdio: 'inherit', timeout: 60000 }
    );

    // Step 2: Seed sessions at key workflow states
    console.log('\nStep 2: Seeding test sessions...');

    const sessions: SeededSessions = {
      draft: runSetupCommand(
        '--state draft --session-id e2e-draft'
      ),
      definingSearch: runSetupCommand(
        '--state defining_search --session-id e2e-defining-search'
      ),
      readyForReviewWf1: runSetupCommand(
        '--state ready_for_review --workflow 1 --num-results 10 --session-id e2e-rfr-wf1'
      ),
      readyForReviewWf2: runSetupCommand(
        '--state ready_for_review --workflow 2 --num-results 10 --session-id e2e-rfr-wf2'
      ),
      underReviewWf2: runSetupCommand(
        '--state under_review --workflow 2 --num-results 10 --agreement-rate 0.5 --session-id e2e-ur-wf2'
      ),
      completedWf1: runSetupCommand(
        '--state completed --workflow 1 --num-results 10 --session-id e2e-comp-wf1'
      ),
      completedWf2: runSetupCommand(
        '--state completed --workflow 2 --num-results 10 --agreement-rate 0.7 --session-id e2e-comp-wf2'
      ),
    };

    // Write session IDs to file for test fixtures
    fs.writeFileSync(SEEDED_SESSIONS_PATH, JSON.stringify(sessions, null, 2));
    console.log('\nSeeded sessions:');
    for (const [key, id] of Object.entries(sessions)) {
      console.log(`  ${key}: ${id}`);
    }

    console.log('\n=== Global setup completed successfully ===\n');
  } catch (error) {
    console.error('\n=== Global setup failed ===');
    console.error(error);
    throw new Error('Failed to set up E2E test environment');
  }
}

export default globalSetup;
