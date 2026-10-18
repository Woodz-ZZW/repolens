export type RunStatus = "hypothesis" | "insufficient_evidence";

export interface Evidence {
  path: string;
  start_line: number;
  end_line: number;
  code: string;
}

export interface Report {
  status: RunStatus;
  summary: string;
  root_cause: string;
  evidence: Evidence[];
  suggestion: string;
  verification: string[];
  missing_information: string[];
}

export interface RunSummary {
  id: number;
  started_at: string;
  model: string;
  status: RunStatus | null;
  elapsed_seconds: number;
  question: string;
}

export interface Run extends RunSummary {
  repo_dir: string;
  model_calls: number;
  tool_calls_used: number;
  report: Report | null;
  error: string | null;
}

export type Loadable<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

type ErrorBody = {
  detail?: string | { loc: (string | number)[]; msg: string }[];
};

function errorMessage(body: ErrorBody | null, status: number): string {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ");
  return `HTTP ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body: ErrorBody | null = await response.json().catch(() => null);
    throw new Error(errorMessage(body, response.status));
  }
  return response.json();
}

export function listRuns(): Promise<RunSummary[]> {
  return request<RunSummary[]>("/api/runs?limit=50");
}

export function getRun(id: number): Promise<Run> {
  return request<Run>(`/api/runs/${id}`);
}

export function createRun(question: string, apiKey: string): Promise<Run> {
  return request<Run>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify({ question }),
  });
}