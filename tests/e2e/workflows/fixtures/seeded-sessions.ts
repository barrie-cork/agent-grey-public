import * as fs from 'fs';
import * as path from 'path';

/**
 * Seeded session IDs from global setup.
 *
 * Global setup creates sessions at key workflow states and writes their
 * IDs to .seeded-sessions.json. This fixture loads those IDs for test consumption.
 */

export interface SeededSessions {
  draft: string;
  definingSearch: string;
  readyForReviewWf1: string;
  readyForReviewWf2: string;
  underReviewWf2: string;
  completedWf1: string;
  completedWf2: string;
}

const SEEDED_SESSIONS_PATH = path.join(__dirname, '../../.seeded-sessions.json');

let _cached: SeededSessions | null = null;

/**
 * Load seeded session IDs from the JSON file written by global setup.
 * Cached after first load.
 */
export function getSeededSessions(): SeededSessions {
  if (_cached) return _cached;

  if (!fs.existsSync(SEEDED_SESSIONS_PATH)) {
    throw new Error(
      `Seeded sessions file not found at ${SEEDED_SESSIONS_PATH}. ` +
      'Run global setup first: npx playwright test --global-setup ./tests/e2e/global-setup.ts'
    );
  }

  const raw = fs.readFileSync(SEEDED_SESSIONS_PATH, 'utf-8');
  _cached = JSON.parse(raw) as SeededSessions;
  return _cached;
}
