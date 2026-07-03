/**
 * Typed API client for the Agent Grey extension ingestion endpoints.
 *
 * All requests include `Authorization: Token <token>` from extension storage.
 * The base URL defaults to the production domain but is overridable in settings.
 */

export interface Session {
  id: string;
  title: string;
  status: string;
  updated_at: string;
}

export interface VisitPayload {
  url: string;
  canonical_url?: string;
  title?: string;
  document_type?: string;
  site_name?: string;
  author?: string;
  published_date?: string;
  accessed_at?: string;
  access_successful?: boolean;
  captured_incognito?: boolean;
  visit_source?: "auto" | "one_click";
  client_capture_id?: string;
  add_to_queue?: boolean;
  justification?: string;
  publisher?: string;
}

export interface IngestResult {
  visits_created: number;
  visits_skipped: number;
  queue_items_added: number;
  errors: string[];
}

export interface AddResultPayload {
  session_id: string;
  url: string;
  title?: string;
  justification?: string;
  metadata?: Record<string, string>;
}

export interface AddResultResponse {
  result_id: string;
  url: string;
}

export class AgentGreyApiClient {
  private baseUrl: string;
  private token: string;

  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}/api/extension${path}`;
    const resp = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Token ${this.token}`,
        ...(options.headers ?? {}),
      },
    });
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`${resp.status} ${resp.statusText}: ${body}`);
    }
    return resp.json() as Promise<T>;
  }

  async getSessions(): Promise<Session[]> {
    return this.request<Session[]>("/sessions/");
  }

  async postVisits(
    sessionId: string,
    visits: VisitPayload[]
  ): Promise<IngestResult> {
    return this.request<IngestResult>("/visits/", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, visits }),
    });
  }

  async addResult(payload: AddResultPayload): Promise<AddResultResponse> {
    return this.request<AddResultResponse>("/add-result/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

/** Load API client from extension storage. Returns null if not configured. */
export async function getApiClient(): Promise<AgentGreyApiClient | null> {
  const { agBaseUrl, agToken } = await chrome.storage.sync.get([
    "agBaseUrl",
    "agToken",
  ]);
  if (!agBaseUrl || !agToken) return null;
  return new AgentGreyApiClient(agBaseUrl as string, agToken as string);
}
