const DEFAULT_BASE_URL = 'http://localhost:8080';

export const AGENYX_API_BASE_URL =
  process.env.NEXT_PUBLIC_AGENYX_API_URL ?? DEFAULT_BASE_URL;

const API_KEY = process.env.NEXT_PUBLIC_AGENYX_API_KEY ?? '';

export interface AgentRunResponse {
  execution_id: string;
  status: string;
}

export interface AgentExecutionState {
  execution_id?: string;
  status?: string;
  intent?: string;
  error?: string;
  answer?: string;
  steps?: string;
  tool_calls?: string;
  [key: string]: string | undefined;
}

export class ApiError extends Error {
  status: number;
  statusText: string;
  details?: unknown;

  constructor(
    message: string,
    status: number,
    statusText: string,
    details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.details = details;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const response = await fetch(`${AGENYX_API_BASE_URL}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      Accept: 'application/json',
      ...(options.body !== undefined
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
    },
    body:
      options.body !== undefined
        ? JSON.stringify(options.body)
        : undefined,
  });

  const rawBody = await response.text();
  let payload: unknown = null;

  try {
    payload = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw new ApiError(
      `Agenyx API request failed with status ${response.status}`,
      response.status,
      response.statusText,
      payload,
    );
  }

  return payload as T;
}

export interface AuthTokens {
  access_token?: string;
  token_type?: string;
  expires_in?: number;
  [key: string]: unknown;
}

export const agentApi = {
  createExecution: (intent: string): Promise<AgentRunResponse> =>
    request<AgentRunResponse>('/v1/agent/run', {
      method: 'POST',
      body: { intent },
    }),

  getExecution: (executionId: string): Promise<AgentExecutionState> =>
    request<AgentExecutionState>(
      `/v1/agent/runs/${encodeURIComponent(executionId)}`,
    ),
};

export const authApi = {
  loginWithEmail: (email: string, password: string): Promise<AuthTokens> =>
    request<AuthTokens>('/auth/email/login', {
      method: 'POST',
      body: { email, password },
    }),

  signupWithEmail: (email: string, password: string): Promise<AuthTokens> =>
    request<AuthTokens>('/auth/email/signup', {
      method: 'POST',
      body: { email, password },
    }),
};
