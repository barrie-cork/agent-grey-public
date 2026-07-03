/**
 * Capture state management.
 * The background worker reads/writes this via chrome.storage.local.
 */

export interface CaptureState {
  active: boolean;
  sessionId: string | null;
  sessionTitle: string | null;
  captureWindowId: number | null;
  /** Whether the capture window is incognito (de-personalised search). */
  capturedIncognito: boolean;
  pendingVisits: PendingVisit[];
  lastFlushAt: string | null;
}

export interface PendingVisit {
  url: string;
  title: string;
  accessed_at: string;
  access_successful: boolean;
  captured_incognito: boolean;
  client_capture_id: string;
}

export const DEFAULT_STATE: CaptureState = {
  active: false,
  sessionId: null,
  sessionTitle: null,
  captureWindowId: null,
  capturedIncognito: false,
  pendingVisits: [],
  lastFlushAt: null,
};

/**
 * Provenance truth: a visit is de-personalised only if its window is actually
 * incognito. A null window (policy-blocked incognito create) is NOT incognito.
 */
export function wasCapturedIncognito(
  win: { incognito?: boolean } | null | undefined
): boolean {
  return win?.incognito === true;
}

export async function loadState(): Promise<CaptureState> {
  const { captureState } = await chrome.storage.local.get("captureState");
  return (captureState as CaptureState | undefined) ?? { ...DEFAULT_STATE };
}

export async function saveState(state: CaptureState): Promise<void> {
  await chrome.storage.local.set({ captureState: state });
}

/** Generate a stable client-side capture ID for idempotency. */
export function makeCaptureId(url: string, accessedAt: string): string {
  return `${accessedAt}|${url}`.replace(/[^a-zA-Z0-9|._~-]/g, "_").slice(0, 64);
}

/** Domains to skip (noisy browser internals, extension pages, etc.). */
const BLOCKLIST = [
  /^chrome:/,
  /^chrome-extension:/,
  /^about:/,
  /^moz-extension:/,
  /^devtools:/,
];

export function shouldCapture(url: string): boolean {
  if (!url) return false;
  return !BLOCKLIST.some((re) => re.test(url));
}
