<template>
  <div class="popup">
    <!-- Settings screen -->
    <template v-if="view === 'settings'">
      <header class="header">
        <span class="logo">Agent Grey</span>
        <button class="btn-back" @click="view = 'main'">&#x2190; Back</button>
      </header>
      <div class="body">
        <label class="field">
          <span class="label">Agent Grey URL</span>
          <input v-model="settingsForm.baseUrl" type="url" placeholder="https://your-domain.com" />
        </label>
        <label class="field">
          <span class="label">API Token</span>
          <input v-model="settingsForm.token" type="password" placeholder="ag_ext_..." />
        </label>
        <button class="btn-primary" @click="saveSettings">Save</button>
        <p v-if="settingsSaved" class="ok">Settings saved.</p>
      </div>
    </template>

    <!-- Add-this-page screen (Stream 2) -->
    <template v-else-if="view === 'add'">
      <header class="header">
        <span class="logo">Agent Grey</span>
        <button class="btn-back" @click="view = 'main'">&#x2190; Back</button>
      </header>
      <div class="body">
        <div class="status status--off">
          Add page to <strong>{{ addSessionTitle }}</strong>
        </div>
        <label class="field">
          <span class="label">Title</span>
          <input v-model="addForm.title" type="text" />
        </label>
        <label class="field">
          <span class="label">Author</span>
          <input v-model="addForm.author" type="text" />
        </label>
        <label class="field">
          <span class="label">Published date</span>
          <input v-model="addForm.published_date" type="date" />
        </label>
        <label class="field">
          <span class="label">Publisher</span>
          <input v-model="addForm.publisher" type="text" />
        </label>
        <label class="field">
          <span class="label">Document type</span>
          <input v-model="addForm.document_type" type="text" />
        </label>
        <label class="field">
          <span class="label">Why added</span>
          <input v-model="addForm.justification" type="text" />
        </label>
        <p class="hint url" :title="addUrl">{{ addUrl }}</p>
        <button class="btn-primary" :disabled="adding" @click="submitAdd">
          {{ adding ? "Adding…" : "Add to screening queue" }}
        </button>
        <p v-if="addError" class="err">{{ addError }}</p>
      </div>
    </template>

    <!-- Main screen -->
    <template v-else>
      <header class="header">
        <span class="logo">Agent Grey</span>
        <button class="btn-icon" title="Settings" @click="view = 'settings'">&#9881;</button>
      </header>

      <div class="body">
        <!-- Not configured -->
        <template v-if="!configured">
          <p class="hint">Enter your Agent Grey URL and API token in settings to get started.</p>
          <button class="btn-primary" @click="view = 'settings'">Open Settings</button>
        </template>

        <!-- Configured -->
        <template v-else>
          <!-- Capturing -->
          <template v-if="capturing">
            <div class="status status--rec">
              <span class="dot dot--rec"></span>
              Recording for <strong>{{ sessionTitle }}</strong>
            </div>
            <p v-if="capturedIncognito" class="hint">
              Incognito window &bull; searches are de-personalised.
            </p>
            <p v-else class="hint warn">
              Normal window &bull; search results may be personalised on this device.
            </p>
            <p class="hint">{{ pendingCount }} visit(s) queued &bull; last flush {{ lastFlush }}</p>
            <button class="btn-danger" @click="stopCapture">Stop capture</button>
          </template>

          <!-- Idle -->
          <template v-else>
            <div class="status status--off">
              <span class="dot dot--off"></span>
              Capture inactive
            </div>

            <label class="field">
              <span class="label">Session</span>
              <select v-model="selectedSessionId">
                <option value="" disabled>Choose a session…</option>
                <option v-for="s in sessions" :key="s.id" :value="s.id">
                  {{ s.title }} ({{ s.status.replaceAll("_", " ") }})
                </option>
              </select>
            </label>

            <button
              class="btn-primary"
              :disabled="!selectedSessionId || loadingSessions"
              @click="startCapture"
            >
              Start capture
            </button>

            <button class="btn-link" @click="loadSessions">
              {{ loadingSessions ? "Loading…" : "Refresh sessions" }}
            </button>

            <p v-if="!incognitoAccess" class="hint warn">
              For de-personalised search, allow this extension in incognito at
              <strong>chrome://extensions</strong> (if your device permits it).
            </p>
          </template>

          <button class="btn-secondary" @click="openAddForm">
            + Add this page
          </button>

          <p v-if="addedNotice" class="ok">{{ addedNotice }}</p>
          <p v-if="error" class="err">{{ error }}</p>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getApiClient, type Session } from "../../utils/api";
import { loadState } from "../../utils/capture";
import { extractMetadata, type PageMetadata } from "../../utils/metadata";

type View = "main" | "settings" | "add";

const view = ref<View>("main");

// Settings
const settingsForm = ref({ baseUrl: "", token: "" });
const settingsSaved = ref(false);
const configured = computed(() => !!settingsForm.value.baseUrl && !!settingsForm.value.token);

// Capture state (synced from background)
const capturing = ref(false);
const activeSessionId = ref<string | null>(null);
const sessionTitle = ref<string | null>(null);
const pendingCount = ref(0);
const lastFlush = ref<string>("never");
const capturedIncognito = ref(false);
// ponytail: isAllowedIncognitoAccess() can't distinguish "toggle off" from
// "policy-disabled" - both return false. The hint is honest either way.
const incognitoAccess = ref(true);

// Add-this-page (Stream 2) state
const addSessionId = ref("");
const addSessionTitle = ref("");
const addUrl = ref("");
const addForm = ref({
  title: "",
  author: "",
  published_date: "",
  publisher: "",
  document_type: "",
  justification: "Added via browser extension",
});
const adding = ref(false);
const addError = ref("");
const addedNotice = ref("");

// Session picker
const sessions = ref<Session[]>([]);
const selectedSessionId = ref("");
const loadingSessions = ref(false);
const error = ref("");

async function loadPersistedSettings() {
  const { agBaseUrl, agToken } = await chrome.storage.sync.get(["agBaseUrl", "agToken"]);
  settingsForm.value.baseUrl = (agBaseUrl as string) ?? "";
  settingsForm.value.token = (agToken as string) ?? "";
}

async function saveSettings() {
  await chrome.storage.sync.set({
    agBaseUrl: settingsForm.value.baseUrl.replace(/\/$/, ""),
    agToken: settingsForm.value.token.trim(),
  });
  settingsSaved.value = true;
  setTimeout(() => (settingsSaved.value = false), 2000);
}

async function syncCaptureState() {
  const state = await loadState();
  capturing.value = state.active;
  activeSessionId.value = state.sessionId;
  sessionTitle.value = state.sessionTitle;
  capturedIncognito.value = state.capturedIncognito;
  pendingCount.value = state.pendingVisits.length;
  lastFlush.value = state.lastFlushAt
    ? new Date(state.lastFlushAt).toLocaleTimeString()
    : "never";
}

async function loadSessions() {
  error.value = "";
  loadingSessions.value = true;
  try {
    const client = await getApiClient();
    if (!client) { error.value = "Not configured – open Settings first."; return; }
    sessions.value = await client.getSessions();
  } catch (e) {
    error.value = String(e);
  } finally {
    loadingSessions.value = false;
  }
}

async function startCapture() {
  if (!selectedSessionId.value) return;
  const session = sessions.value.find((s) => s.id === selectedSessionId.value);
  if (!session) return;
  error.value = "";
  // Request webNavigation from popup (user gesture context required in MV3).
  // Without it the background cannot record visits, so a denial must not
  // start a capture that would show "Recording" while capturing nothing.
  let granted = false;
  try {
    granted = await chrome.permissions.request({
      permissions: ["webNavigation"],
    });
  } catch {
    granted = false;
  }
  if (!granted) {
    error.value = "Capture permission was not granted.";
    return;
  }
  // sendMessage may not resolve if the new capture window steals focus and
  // closes the popup - fire-and-forget, then sync state.
  chrome.runtime.sendMessage({
    type: "START_CAPTURE",
    sessionId: session.id,
    sessionTitle: session.title,
  });
  // Small delay to let background save state before we read it
  await new Promise((r) => setTimeout(r, 300));
  await syncCaptureState();
}

async function stopCapture() {
  error.value = "";
  await chrome.runtime.sendMessage({ type: "STOP_CAPTURE" });
  await syncCaptureState();
}

async function openAddForm() {
  error.value = "";
  // Target the active session when capturing, else the picked one.
  const sessionId = capturing.value ? activeSessionId.value : selectedSessionId.value;
  if (!sessionId) {
    error.value = "Choose a session first.";
    return;
  }
  const sessTitle = capturing.value
    ? (sessionTitle.value ?? "")
    : (sessions.value.find((s) => s.id === selectedSessionId.value)?.title ?? "");

  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id || !tab.url) {
    error.value = "No active page to add.";
    return;
  }

  // Extract metadata from the live page; injection can fail on restricted
  // pages (chrome://, web store) - fall back to the tab's own title/url.
  let md: Partial<PageMetadata> = {};
  try {
    const [inj] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractMetadata,
    });
    md = (inj?.result as PageMetadata) ?? {};
  } catch {
    md = {};
  }

  addSessionId.value = sessionId;
  addSessionTitle.value = sessTitle;
  // Prefer the page's canonical URL: the add-result duplicate guard is an
  // exact url match, so raw tab URLs with tracking params dodge the 409.
  addUrl.value = md.canonical_url || tab.url;
  addForm.value = {
    title: md.title || tab.title || "",
    author: md.author || "",
    published_date: md.published_date || "",
    publisher: md.publisher || "",
    document_type: md.document_type || "",
    justification: "Added via browser extension",
  };
  addError.value = "";
  view.value = "add";
}

async function submitAdd() {
  addError.value = "";
  adding.value = true;
  try {
    const client = await getApiClient();
    if (!client) {
      addError.value = "Not configured – open Settings first.";
      return;
    }
    await client.addResult({
      session_id: addSessionId.value,
      url: addUrl.value,
      title: addForm.value.title || addUrl.value,
      justification: addForm.value.justification || "Added via browser extension",
      metadata: {
        author: addForm.value.author,
        published_date: addForm.value.published_date,
        publisher: addForm.value.publisher,
        document_type: addForm.value.document_type,
      },
    });
    view.value = "main";
    addedNotice.value = "Page added to screening queue.";
    setTimeout(() => (addedNotice.value = ""), 3000);
  } catch (e) {
    addError.value = String(e).includes("409")
      ? "This page is already in the session."
      : String(e);
  } finally {
    adding.value = false;
  }
}

onMounted(async () => {
  await loadPersistedSettings();
  await syncCaptureState();
  incognitoAccess.value = await chrome.extension
    .isAllowedIncognitoAccess()
    .catch(() => true);
  if (configured.value && !capturing.value) await loadSessions();
});
</script>

<style scoped>
.popup { padding: 0; }
.header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-bottom: 1px solid #e5e7eb; background: #1e3a5f;
  color: #fff;
}
.logo { font-weight: 700; font-size: 14px; }
.btn-icon { background: none; border: none; color: #fff; cursor: pointer; font-size: 16px; }
.btn-back { background: none; border: none; color: #fff; cursor: pointer; font-size: 12px; }
.body { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.status { display: flex; align-items: center; gap: 6px; font-size: 13px; padding: 6px 8px; border-radius: 6px; }
.status--rec { background: #fee2e2; color: #991b1b; }
.status--off { background: #f3f4f6; color: #6b7280; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot--rec { background: #dc2626; animation: pulse 1.5s ease-in-out infinite; }
.dot--off { background: #9ca3af; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.field { display: flex; flex-direction: column; gap: 3px; }
.label { font-size: 12px; font-weight: 500; color: #374151; }
input, select {
  border: 1px solid #d1d5db; border-radius: 6px; padding: 5px 8px;
  font-size: 13px; outline: none;
}
input:focus, select:focus { border-color: #1e3a5f; }
.btn-primary {
  background: #1e3a5f; color: #fff; border: none; border-radius: 6px;
  padding: 7px 12px; font-size: 13px; cursor: pointer;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary:not(:disabled):hover { background: #163058; }
.btn-danger {
  background: #dc2626; color: #fff; border: none; border-radius: 6px;
  padding: 7px 12px; font-size: 13px; cursor: pointer;
}
.btn-secondary {
  background: #fff; color: #1e3a5f; border: 1px solid #1e3a5f; border-radius: 6px;
  padding: 7px 12px; font-size: 13px; cursor: pointer;
}
.btn-secondary:hover { background: #f1f5fb; }
.btn-link { background: none; border: none; color: #1e3a5f; font-size: 12px; cursor: pointer; padding: 0; }
.hint { font-size: 12px; color: #6b7280; margin: 0; }
.hint.warn { color: #b45309; }
.url { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ok { font-size: 12px; color: #16a34a; margin: 0; }
.err { font-size: 12px; color: #dc2626; margin: 0; }
</style>
