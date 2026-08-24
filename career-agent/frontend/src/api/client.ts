// Base fetch wrapper. All requests go through the /api prefix, which
// vite.config.ts proxies to the local FastAPI backend (localhost:8000)
// -- same-origin from the browser's perspective, so no CORS round-trip
// is needed in dev. CORSMiddleware on the backend exists as a fallback
// for calling it directly outside the proxy.

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed with status ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: unknown
    try {
      const body = await response.json()
      detail = body.detail ?? body
    } catch {
      detail = response.statusText
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  return handleResponse<T>(response)
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body !== undefined ? JSON.stringify(body) : undefined }),
  // No Content-Type header here on purpose -- the browser sets
  // multipart/form-data with the correct boundary itself when the body
  // is a FormData instance, and overriding it manually breaks the upload.
  upload: <T>(path: string, form: FormData) => fetch(`/api${path}`, { method: 'POST', body: form }).then((r) => handleResponse<T>(r)),
}
