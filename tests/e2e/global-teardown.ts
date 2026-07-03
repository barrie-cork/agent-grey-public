/**
 * Playwright Global Teardown
 *
 * Runs once after all E2E tests to clean up test data.
 * Calls teardown_e2e_data management command which deletes:
 * - Sessions with 'E2E' in title (and all cascaded objects)
 * - Users with e2e- username prefix
 * - E2E test organisation
 *
 * Also removes the seeded sessions JSON file.
 */

import { FullConfig } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import { SEEDED_SESSIONS_PATH } from './global-setup';

async function globalTeardown(config: FullConfig) {
  console.log('\n=== E2E Global Teardown ===');

  try {
    // Run Django management command to delete all E2E test data
    execSync(
      'docker compose exec -T web python manage.py teardown_e2e_data',
      { stdio: 'inherit', timeout: 60000 }
    );

    // Clean up seeded sessions file
    if (fs.existsSync(SEEDED_SESSIONS_PATH)) {
      fs.unlinkSync(SEEDED_SESSIONS_PATH);
      console.log('Removed seeded sessions file');
    }

    console.log('\n=== Global teardown completed successfully ===\n');
  } catch (error) {
    console.error('\n=== Global teardown failed ===');
    console.error(error);
    // Don't throw -- teardown failures should not mask test failures
  }
}

export default globalTeardown;
