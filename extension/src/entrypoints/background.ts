/**
 * Background service worker (MV3).
 *
 * Responsibilities:
 * - Track the dedicated capture window.
 * - On webNavigation.onCompleted inside the capture window, record a visit.
 * - Flush the pending-visit buffer to the server every FLUSH_INTERVAL_MS or
 *   when the buffer reaches FLUSH_BATCH_SIZE.
 * - Expose a chrome.runtime.onMessage handler so the popup can start/stop
 *   capture and trigger an immediate flush.
 */

import { getApiClient } from "../utils/api";
import {
  DEFAULT_STATE,
  loadState,
  makeCaptureId,
  saveState,
  shouldCapture,
  wasCapturedIncognito,
  type CaptureState,
} from "../utils/capture";

export default defineBackground(() => {
  const FLUSH_INTERVAL_MS = 30_000; // 30 s
  const FLUSH_BATCH_SIZE = 50;

  // ponytail: badge is the only always-visible privacy signal
  function setBadgeCapturing(active: boolean) {
    if (active) {
      chrome.action.setBadgeText({ text: "REC" });
      chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
    } else {
      chrome.action.setBadgeText({ text: "" });
    }
  }

  /**
   * Open the dedicated capture window, opening it incognito when the extension
   * is allowed (clean cookie jar = de-personalised search). The window opens to
   * a pinned status tab so the user can never confuse it with a personal window.
   *
   * Incognito create does NOT throw when blocked by policy - it resolves to a
   * window the extension cannot control, or to null. So we null-check (and catch
   * the rare throw) and fall back to a normal window.
   */
  async function openCaptureWindow(): Promise<chrome.windows.Window | null> {
    const url = chrome.runtime.getURL("status.html");
    let win: chrome.windows.Window | null = null;

    const allowed = await chrome.extension
      .isAllowedIncognitoAccess()
      .catch(() => false);
    if (allowed) {
      win = await chrome.windows
        .create({ url, type: "normal", incognito: true })
        .catch(() => null);
    }
    if (!win) {
      win = await chrome.windows.create({ url, type: "normal" });
    }

    // Pin the status tab so it stays put as the user opens browsing tabs.
    const statusTabId = win?.tabs?.[0]?.id;
    if (statusTabId != null) {
      await chrome.tabs.update(statusTabId, { pinned: true }).catch(() => {});
    }
    return win;
  }

  // -------------------------------------------------------------------------
  // Message handler (popup <-> background)
  // -------------------------------------------------------------------------

  chrome.runtime.onMessage.addListener(
    (msg: Record<string, unknown>, _sender, sendResponse) => {
      (async () => {
        switch (msg.type) {
          case "START_CAPTURE": {
            const { sessionId, sessionTitle } = msg as {
              sessionId: string;
              sessionTitle: string;
            };
            const win = await openCaptureWindow();
            const capturedIncognito = wasCapturedIncognito(win);
            const state: CaptureState = {
              ...DEFAULT_STATE,
              active: true,
              sessionId,
              sessionTitle,
              captureWindowId: win?.id ?? null,
              capturedIncognito,
              pendingVisits: [],
            };
            await saveState(state);
            setBadgeCapturing(true);
            attachNavListener();
            sendResponse({
              ok: true,
              windowId: win?.id,
              incognito: capturedIncognito,
            });
            break;
          }

          case "STOP_CAPTURE": {
            const state = await loadState();
            await flush(state);
            await saveState({ ...DEFAULT_STATE });
            setBadgeCapturing(false);
            revokeWebNavPermission();
            sendResponse({ ok: true });
            break;
          }

          case "FLUSH": {
            const state = await loadState();
            const result = await flush(state);
            sendResponse({ ok: true, result });
            break;
          }

          case "GET_STATE": {
            const state = await loadState();
            sendResponse(state);
            break;
          }

          default:
            sendResponse({ error: "Unknown message type" });
        }
      })();
      return true; // keep channel open for async response
    }
  );

  // -------------------------------------------------------------------------
  // webNavigation listener (visit capture)
  // -------------------------------------------------------------------------

  function attachNavListener() {
    if (chrome.webNavigation?.onCompleted?.hasListener(onNavCompleted)) return;
    chrome.webNavigation?.onCompleted?.addListener(onNavCompleted, {
      url: [{ schemes: ["http", "https"] }],
    });
  }

  async function onNavCompleted(
    details: chrome.webNavigation.WebNavigationFramedCallbackDetails
  ) {
    if (details.frameId !== 0) return; // main frame only
    const state = await loadState();
    if (!state.active || state.captureWindowId == null) return;

    // Check tab belongs to the capture window
    const tab = await chrome.tabs.get(details.tabId).catch(() => null);
    if (!tab || tab.windowId !== state.captureWindowId) return;

    const { url } = details;
    if (!shouldCapture(url)) return;

    const now = new Date().toISOString();
    const visit = {
      url,
      title: tab.title ?? "",
      accessed_at: now,
      access_successful: true,
      captured_incognito: state.capturedIncognito,
      client_capture_id: makeCaptureId(url, now),
    };

    const updated: CaptureState = {
      ...state,
      pendingVisits: [...state.pendingVisits, visit],
    };
    await saveState(updated);

    if (updated.pendingVisits.length >= FLUSH_BATCH_SIZE) {
      await flush(updated);
    }
  }

  // -------------------------------------------------------------------------
  // Periodic flush alarm
  // -------------------------------------------------------------------------

  chrome.alarms.create("agFlush", { periodInMinutes: 0.5 }); // 30 s
  chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (alarm.name !== "agFlush") return;
    const state = await loadState();
    if (state.active && state.pendingVisits.length > 0) {
      await flush(state);
    }
  });

  // -------------------------------------------------------------------------
  // Flush helper
  // -------------------------------------------------------------------------

  async function flush(state: CaptureState) {
    if (!state.sessionId || state.pendingVisits.length === 0) return null;
    const client = await getApiClient();
    if (!client) return null;

    const visits = [...state.pendingVisits];
    try {
      const result = await client.postVisits(state.sessionId, visits);
      // Only clear visits that were successfully sent
      const remaining = state.pendingVisits.slice(visits.length);
      await saveState({
        ...state,
        pendingVisits: remaining,
        lastFlushAt: new Date().toISOString(),
      });
      return result;
    } catch (err) {
      console.error("[AG] flush failed:", err);
      return null;
    }
  }

  // -------------------------------------------------------------------------
  // Optional permission helpers
  // -------------------------------------------------------------------------

  function requestWebNavPermission() {
    return new Promise<boolean>((resolve) => {
      chrome.permissions.request(
        { permissions: ["webNavigation"] },
        (granted) => {
          if (granted) attachNavListener();
          resolve(granted);
        }
      );
    });
  }

  function revokeWebNavPermission() {
    chrome.permissions.remove({ permissions: ["webNavigation"] });
  }

  // Auto-stop capture when the dedicated capture window is closed
  chrome.windows.onRemoved.addListener(async (windowId) => {
    const state = await loadState();
    if (state.active && state.captureWindowId === windowId) {
      await flush(state);
      // flush() awaited the network: reload before clearing so we neither
      // wipe a capture started meanwhile nor drop visits a failed flush
      // left queued in storage.
      const latest = await loadState();
      if (
        latest.sessionId !== state.sessionId ||
        latest.captureWindowId !== windowId
      ) {
        return;
      }
      await saveState(
        latest.pendingVisits.length > 0
          ? { ...latest, active: false, captureWindowId: null }
          : { ...DEFAULT_STATE },
      );
      setBadgeCapturing(false);
      revokeWebNavPermission();
    }
  });

  // Restore badge + listener on service worker restart
  loadState().then((state) => {
    if (state.active) {
      attachNavListener();
      setBadgeCapturing(true);
    }
  });
});
