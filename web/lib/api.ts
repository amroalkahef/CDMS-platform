import { AuthUser, clearSession, getToken, redirectToLogin } from "./auth";
import { ApiError } from "./errors";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

/** backend/app/errors.py and ai-platform/app/errors.py both shape failed
 * responses as `{"detail": {"error_code": "...", "params": {...}}}` — pull
 * that out so the UI can translate it instead of showing raw server text. */
async function parseErrorDetail(res: Response): Promise<{ code: string; params?: Record<string, string | number> } | null> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object" && typeof detail.error_code === "string") {
      return { code: detail.error_code, params: detail.params };
    }
  } catch {
    // response wasn't JSON (or had no structured detail) — caller falls back to a generic message
  }
  return null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
    cache: "no-store",
  });
  if (res.status === 401) {
    // Only an *authenticated* request being rejected means the session
    // expired/is invalid. A 401 with no token attached (e.g. a failed
    // /api/auth/login) is a normal credential error, not a stale session —
    // clearing/redirecting here would bounce the user off the login page
    // mid-attempt instead of showing them "incorrect email or password".
    if (token) {
      clearSession();
      redirectToLogin();
      throw new ApiError("notAuthenticated", 401);
    }
    const structured = await parseErrorDetail(res);
    throw new ApiError(structured?.code ?? "requestFailed", 401, structured?.params);
  }
  if (!res.ok) {
    const structured = await parseErrorDetail(res);
    throw new ApiError(structured?.code ?? "requestFailed", res.status, structured?.params);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export interface DraftResult {
  task_type: string;
  draft: string;
  references: { document_id: string; title: string; similarity: number }[];
  confidence: number;
  validation_issues: { severity: string; category: string; message: string }[];
  retrieved_docs: {
    document_id: string;
    title: string;
    doc_type: string;
    chunk_content: string;
    similarity: number;
  }[];
  trace: Record<string, unknown>[];
}

export interface WorkflowStep {
  id: string;
  step_order: number;
  role: string;
  status: string;
  decided_by: string | null;
  decided_at: string | null;
  comment: string | null;
}

export interface Workflow {
  id: string;
  entity_type: string;
  entity_id: string;
  title: string;
  status: string;
  current_step_order: number;
  requested_by: string;
  created_at: string;
  updated_at: string;
  steps: WorkflowStep[];
}

export interface DocumentVersion {
  version: number;
  title: string;
  content: string;
  status: string;
  created_by: string;
  created_at: string;
}

export interface Notification {
  id: string;
  channel: string;
  subject: string;
  body: string;
  status: string;
  related_workflow_id: string | null;
  created_at: string;
}

export interface Circular {
  id: string;
  entity_type: "circular";
  circular_number: string | null;
  title: string;
  content: string;
  department: string;
  frequency: string;
  publication_date: string | null;
  status: string;
  version: number;
  created_by: string;
  references: Record<string, unknown>[];
  created_at: string;
  published_at: string | null;
  workflow_id?: string | null;
}

export interface Decision {
  id: string;
  entity_type: "decision";
  decision_number: string | null;
  title: string;
  content: string;
  department: string;
  effective_date: string | null;
  status: string;
  version: number;
  created_by: string;
  references: Record<string, unknown>[];
  created_at: string;
  published_at: string | null;
  workflow_id?: string | null;
}

export interface SimilarityHit {
  id: string;
  title: string;
  department: string;
  status: string;
  similarity: number;
  verdict: "duplicate" | "related" | "different" | "unknown";
  explanation: string | null;
  is_likely_duplicate: boolean;
}

export interface Constants {
  departments: string[];
  circular_frequencies: string[];
  circular_statuses: string[];
  decision_statuses: string[];
}

export interface ActivityItem {
  action: string;
  detail: string;
  user: string;
  timestamp: string;
}

export interface UpcomingDeadline {
  id: string;
  title: string;
  department: string;
  publication_date: string;
}

export interface Stats {
  total_circulars: number;
  total_decisions: number;
  pending_drafts: number;
  published: number;
  recent_activity: ActivityItem[];
  upcoming_deadlines: UpcomingDeadline[];
}

export interface ChatEvent {
  type: "tool_call" | "token" | "error" | "done";
  tool?: string;
  content?: string;
  message?: string;
  error_code?: string;
}

/** Manual fetch + ReadableStream SSE parsing — EventSource can't send the
 * Authorization header this app keeps in localStorage, so it isn't usable
 * here. */
async function chatStream(
  messages: { role: string; content: string }[],
  onEvent: (event: ChatEvent) => void,
  language?: string
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BACKEND_URL}/api/ai/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ messages, language }),
  });
  if (res.status === 401) {
    clearSession();
    redirectToLogin();
    throw new ApiError("notAuthenticated", 401);
  }
  if (!res.ok || !res.body) {
    const structured = await parseErrorDetail(res);
    throw new ApiError(structured?.code ?? "requestFailed", res.status, structured?.params);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // {stream: true} is required so multi-byte UTF-8 characters split across
    // chunk boundaries decode correctly instead of turning into replacement chars.
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const json = line.slice(5).trim();
      if (!json) continue;
      onEvent(JSON.parse(json) as ChatEvent);
    }
  }
}

export const api = {
  chatStream,

  draft: (payload: {
    task_type: string;
    user_prompt: string;
    doc_type_filter?: string;
    required_sections?: string[];
    language?: string;
  }) => request<DraftResult>("/api/ai/draft", { method: "POST", body: JSON.stringify(payload) }),

  execute: (payload: {
    entity_type: string;
    title: string;
    content: string;
    references: { document_id: string; title: string; similarity: number }[];
  }) =>
    request<{ entity_id: string; entity_type: string; status: string; workflow_id: string | null }>(
      "/api/ai/execute",
      { method: "POST", body: JSON.stringify(payload) }
    ),

  search: (q: string, docType?: string) =>
    request<{ query: string; results: Record<string, unknown>[] }>(
      `/api/ai/search?q=${encodeURIComponent(q)}${docType ? `&doc_type=${encodeURIComponent(docType)}` : ""}`
    ),

  ingest: (payload: { title: string; doc_type: string; source: string; content: string }) =>
    request<{ document_id: string; chunks_created: number }>("/api/ai/documents/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  uploadDocument: async (file: File, docType: string, title?: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);
    if (title) form.append("title", title);
    const token = getToken();
    const res = await fetch(`${BACKEND_URL}/api/ai/documents/upload`, {
      method: "POST",
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (res.status === 401) {
      clearSession();
      redirectToLogin();
      throw new ApiError("notAuthenticated", 401);
    }
    if (!res.ok) {
      const structured = await parseErrorDetail(res);
      throw new ApiError(structured?.code ?? "requestFailed", res.status, structured?.params);
    }
    return res.json() as Promise<{ document_id: string; chunks_created: number }>;
  },

  listWorkflows: (entityId?: string) =>
    request<Workflow[]>(`/api/workflows${entityId ? `?entity_id=${entityId}` : ""}`),

  decideWorkflow: (id: string, approve: boolean, comment?: string) =>
    request<Workflow>(`/api/workflows/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ approve, comment }),
    }),

  listNotifications: () => request<Notification[]>("/api/notifications"),

  markNotification: (id: string, status: "read" | "archived") =>
    request<Notification>(`/api/notifications/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),

  listVersions: (entityType: string, entityId: string) =>
    request<{ entity_type: string; entity_id: string; versions: DocumentVersion[] }>(
      `/api/ai/documents/${entityType}/${entityId}/versions`
    ),

  getConstants: () => request<Constants>("/api/ai/constants"),

  getStats: () => request<Stats>("/api/ai/stats"),

  checkSimilarity: (payload: { entity_type: "circular" | "decision"; title: string; content: string; exclude_id?: string }) =>
    request<{ results: SimilarityHit[] }>("/api/ai/similarity-check", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listCirculars: (filters?: { status?: string; department?: string; q?: string }) => {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.department) params.set("department", filters.department);
    if (filters?.q) params.set("q", filters.q);
    const qs = params.toString();
    return request<Circular[]>(`/api/ai/circulars${qs ? `?${qs}` : ""}`);
  },

  getCircular: (id: string) => request<Circular>(`/api/ai/circulars/${id}`),

  createCircular: (payload: Partial<Circular> & { title: string; content: string }) =>
    request<Circular>("/api/ai/circulars", { method: "POST", body: JSON.stringify(payload) }),

  updateCircular: (id: string, payload: Partial<Circular>) =>
    request<Circular>(`/api/ai/circulars/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  deleteCircular: (id: string) => request<void>(`/api/ai/circulars/${id}`, { method: "DELETE" }),

  listDecisions: (filters?: { status?: string; department?: string; q?: string }) => {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.department) params.set("department", filters.department);
    if (filters?.q) params.set("q", filters.q);
    const qs = params.toString();
    return request<Decision[]>(`/api/ai/decisions${qs ? `?${qs}` : ""}`);
  },

  getDecision: (id: string) => request<Decision>(`/api/ai/decisions/${id}`),

  createDecision: (payload: Partial<Decision> & { title: string; content: string }) =>
    request<Decision>("/api/ai/decisions", { method: "POST", body: JSON.stringify(payload) }),

  updateDecision: (id: string, payload: Partial<Decision>) =>
    request<Decision>(`/api/ai/decisions/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  deleteDecision: (id: string) => request<void>(`/api/ai/decisions/${id}`, { method: "DELETE" }),

  publishCircular: (id: string) => request<Circular>(`/api/ai/circulars/${id}/publish`, { method: "POST" }),

  publishDecision: (id: string) => request<Decision>(`/api/ai/decisions/${id}/publish`, { method: "POST" }),

  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string; user: AuthUser }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (name: string, email: string, password: string, role: "editor" | "reviewer") =>
    request<{ access_token: string; token_type: string; user: AuthUser }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password, role }),
    }),

  me: () => request<AuthUser>("/api/auth/me"),
};
