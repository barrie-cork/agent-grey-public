import { Page } from '@playwright/test';

/**
 * Vue SPA Testing Helpers
 *
 * These helpers ensure proper handling of Vue.js Single Page Application (SPA)
 * lifecycle when testing with Playwright. The application uses Vue Router with
 * client-side routing mounted at /screening/.
 *
 * Key Architecture:
 * - Server-side route: /screening/ (serves Vue SPA container)
 * - Client-side routes: /screening/work-queue, /screening/conflicts, etc.
 * - Vue Router base path: /screening/
 * - Django catch-all pattern serves same HTML for all /screening/* paths
 */

/**
 * Wait for Vue SPA to initialize and be ready
 *
 * This function waits for:
 * 1. The #app element to exist in the DOM
 * 2. Vue to render content inside the #app element
 *
 * @param page - Playwright Page instance
 * @param timeout - Maximum time to wait (default: 10000ms)
 */
export async function waitForVueSPA(
  page: Page,
  timeout: number = 10000
): Promise<void> {
  // Wait for Vue app container to exist
  await page.waitForSelector('#app', { timeout });

  // Wait for Vue to render content (app must have child nodes)
  await page.waitForFunction(() => {
    const app = document.querySelector('#app');
    return app && app.childNodes.length > 0;
  }, { timeout });
}

/**
 * Navigate to a Vue Router SPA route and wait for it to be ready
 *
 * This function:
 * 1. Constructs the full URL with /screening/ prefix
 * 2. Navigates to the route
 * 3. Waits for Vue SPA to initialize
 * 4. Verifies the route is active
 *
 * @param page - Playwright Page instance
 * @param route - Vue Router path (e.g., '/conflicts', '/work-queue')
 *                Should NOT include the /screening/ prefix
 *
 * @example
 * await navigateToSPARoute(page, '/conflicts');
 * // Navigates to /screening/conflicts and waits for Vue Router
 */
export async function navigateToSPARoute(
  page: Page,
  route: string
): Promise<void> {
  // Ensure route starts with /
  const normalizedRoute = route.startsWith('/') ? route : `/${route}`;

  // Construct full URL with /screening/ prefix
  const fullUrl = `/screening${normalizedRoute}`;

  // Navigate to the route
  await page.goto(fullUrl);

  // Wait for Vue SPA to initialize
  await waitForVueSPA(page);

  // Wait for Vue Router to activate the route
  // Check that the URL matches what we expect
  await page.waitForFunction((expectedRoute) => {
    return window.location.pathname === expectedRoute;
  }, fullUrl, { timeout: 5000 });
}

/**
 * Wait for a Vue component to mount and render
 *
 * This function waits for a specific element to appear in the DOM
 * and become visible. Use this after navigation or any action that
 * triggers component mounting.
 *
 * @param page - Playwright Page instance
 * @param selector - CSS selector or data-testid selector
 * @param timeout - Maximum time to wait (default: 10000ms)
 *
 * @example
 * await waitForVueComponent(page, '[data-testid="conflict-header"]');
 */
export async function waitForVueComponent(
  page: Page,
  selector: string,
  timeout: number = 10000
): Promise<void> {
  await page.waitForSelector(selector, {
    timeout,
    state: 'visible'
  });
}

/**
 * Wait for SSE (Server-Sent Events) connection to establish
 *
 * This function waits for the SSE connection status indicator to show
 * as connected. Use this when testing real-time features that depend
 * on SSE being active.
 *
 * @param page - Playwright Page instance
 * @param timeout - Maximum time to wait (default: 5000ms)
 *
 * @example
 * await navigateToSPARoute(page, '/conflicts/123/discuss');
 * await waitForVueComponent(page, '[data-testid="conflict-header"]');
 * await waitForSSEReady(page);
 */
export async function waitForSSEReady(
  page: Page,
  timeout: number = 5000
): Promise<void> {
  // Check if SSE status indicator exists
  const hasSSEIndicator = await page.locator('[data-testid="sse-status"]').count();

  if (hasSSEIndicator > 0) {
    // Wait for status to show connected
    await page.waitForSelector('[data-testid="sse-status"]:has-text("connected"), [data-testid="sse-status"]:has-text("active")', {
      timeout,
    });
  } else {
    // If no indicator, just wait a bit for connection to establish
    // This is a fallback for components that don't expose SSE status
    await page.waitForTimeout(1000);
  }
}

/**
 * Wait for an API response to complete
 *
 * Helper for waiting for specific API calls to finish, useful when
 * testing forms and mutations that trigger backend updates.
 *
 * @param page - Playwright Page instance
 * @param urlPattern - RegExp or string pattern to match URL
 * @param expectedStatus - Expected HTTP status code (default: 200)
 * @param timeout - Maximum time to wait (default: 10000ms)
 *
 * @example
 * await page.click('[data-testid="post-comment-btn"]');
 * await waitForAPIResponse(page, /\/api\/consensus\//, 201);
 */
export async function waitForAPIResponse(
  page: Page,
  urlPattern: string | RegExp,
  expectedStatus: number = 200,
  timeout: number = 10000
): Promise<void> {
  await page.waitForResponse(response => {
    const urlMatches = typeof urlPattern === 'string'
      ? response.url().includes(urlPattern)
      : urlPattern.test(response.url());
    return urlMatches && response.status() === expectedStatus;
  }, { timeout });
}

/**
 * Verify that organisation data is loaded in the browser
 *
 * Checks multiple indicators to ensure organisation context is available:
 * 1. localStorage has currentOrganisation data
 * 2. #user-data script tag contains organisation info
 * 3. Vue app is mounted
 *
 * @param page - Playwright Page instance
 * @throws Error if organisation data is missing
 *
 * @example
 * await ensureOrganisationContext(page);
 * await verifyOrganisationLoaded(page);
 */
export async function verifyOrganisationLoaded(page: Page): Promise<void> {
  const orgState = await page.evaluate(() => {
    // Check localStorage
    let localStorageOrg = null;
    try {
      const orgData = localStorage.getItem('currentOrganisation');
      localStorageOrg = orgData ? JSON.parse(orgData) : null;
    } catch (e) {
      console.error('Failed to parse localStorage organisation:', e);
    }

    // Check user-data element
    let userDataOrg = null;
    try {
      const userData = document.getElementById('user-data');
      if (userData) {
        const data = JSON.parse(userData.textContent || '{}');
        userDataOrg = data.organisation || null;
      }
    } catch (e) {
      console.error('Failed to parse user-data:', e);
    }

    return {
      localStorage: localStorageOrg,
      userDataElement: !!document.getElementById('user-data'),
      userDataOrg: userDataOrg,
      appMounted: !!document.querySelector('#app > *')
    };
  });

  console.log('[verifyOrganisationLoaded] Organisation state:', orgState);

  if (!orgState.localStorage && !orgState.userDataOrg) {
    throw new Error('Organisation not found in localStorage or user-data element');
  }

  if (!orgState.userDataElement) {
    throw new Error('user-data element not found in DOM');
  }

  if (!orgState.appMounted) {
    throw new Error('Vue app not mounted');
  }

  console.log('[verifyOrganisationLoaded] ✅ Organisation context verified');
}

/**
 * Ensure organisation context is loaded
 *
 * Vue Router navigation guards check for organisation context and
 * redirect to /organisation/select/ if not present. This function
 * handles that scenario by selecting the E2E test organisation.
 *
 * Now includes explicit verification that organisation data is loaded
 * before proceeding.
 *
 * @param page - Playwright Page instance
 *
 * @example
 * await loginAsReviewer(page);
 * await ensureOrganisationContext(page);
 * await navigateToSPARoute(page, '/work-queue');
 */
export async function ensureOrganisationContext(page: Page): Promise<void> {
  try {
    // Navigate to screening SPA to trigger any redirects
    await page.goto('/screening/', { waitUntil: 'networkidle', timeout: 15000 });

    // Wait a moment for potential redirect
    await page.waitForTimeout(2000);

    // Check if we were redirected to organisation selection
    const currentUrl = page.url();

    if (currentUrl.includes('/organisation/select/')) {
      // Select the first available organisation (E2E Test Organisation)
      // This assumes the organisation selector has a data-testid attribute
      const orgSelector = '[data-testid="select-org"]';

      // Wait for org selection page to load
      await page.waitForSelector(orgSelector, { timeout: 10000 });

      // Click to select organisation
      await page.click(orgSelector);

      // Wait for redirect back to screening
      await page.waitForURL('/screening/', { timeout: 10000 });
    }

    // Check if we got redirected to logout (auth issue)
    if (currentUrl.includes('/accounts/logout') || currentUrl.includes('/accounts/login')) {
      throw new Error(`Authentication issue: redirected to ${currentUrl}`);
    }

    // Ensure Vue SPA is ready
    await waitForVueSPA(page, 15000);

    // NEW: Wait for organisation to be loaded in localStorage
    console.log('[ensureOrganisationContext] Waiting for organisation in localStorage...');
    try {
      await page.waitForFunction(() => {
        const orgData = localStorage.getItem('currentOrganisation');
        if (!orgData) return false;
        try {
          const org = JSON.parse(orgData);
          return org && org.id;
        } catch {
          return false;
        }
      }, { timeout: 10000 });
    } catch (error) {
      const debugState = await page.evaluate(() => ({
        currentUrl: window.location.href,
        localStorage: { ...localStorage },
        hasUserData: !!document.getElementById('user-data'),
        currentOrganisation: localStorage.getItem('currentOrganisation'),
      }));
      console.error('[ensureOrganisationContext] localStorage timeout. Debug state:', debugState);
      throw new Error(`Organisation context failed (localStorage): ${JSON.stringify(debugState)}`);
    }

    // NEW: Verify organisation is accessible in user-data
    console.log('[ensureOrganisationContext] Verifying user-data element...');
    try {
      await page.waitForFunction(() => {
        const userData = document.getElementById('user-data');
        if (!userData) return false;
        try {
          const data = JSON.parse(userData.textContent || '{}');
          return data.organisation && data.organisation.id;
        } catch {
          return false;
        }
      }, { timeout: 10000 });
    } catch (error) {
      const debugState = await page.evaluate(() => {
        const userData = document.getElementById('user-data');
        return {
          currentUrl: window.location.href,
          hasUserDataElement: !!userData,
          userDataContent: userData?.textContent || 'null',
          organisationInStorage: localStorage.getItem('currentOrganisation'),
        };
      });
      console.error('[ensureOrganisationContext] user-data timeout. Debug state:', debugState);
      throw new Error(`Organisation context failed (user-data): ${JSON.stringify(debugState)}`);
    }

    console.log('[ensureOrganisationContext] ✅ Organisation context ready');
  } catch (error) {
    console.error('Error in ensureOrganisationContext:', error);
    throw error;
  }
}

/**
 * Navigate using client-side Vue Router navigation
 *
 * Instead of using page.goto(), this function triggers navigation
 * through clicking a link or programmatically updating the route.
 * This more closely mimics real user behaviour.
 *
 * @param page - Playwright Page instance
 * @param targetRoute - The target route path (e.g., '/conflicts')
 *
 * @example
 * await navigateViaSPALink(page, '/conflicts');
 */
export async function navigateViaSPALink(
  page: Page,
  targetRoute: string
): Promise<void> {
  // Find and click a link that goes to the target route
  const linkSelector = `a[href*="${targetRoute}"]`;
  await page.click(linkSelector);

  // Wait for Vue Router navigation to complete
  await page.waitForURL(`/screening${targetRoute}`, { timeout: 5000 });
}
