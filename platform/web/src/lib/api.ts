import type {
  Backtest,
  Competition,
  Match,
  ModelVersion,
  Overview,
  Prediction,
  QualityIssue,
  TeamDetail,
  TeamSummary,
  User,
  Favorite,
  Notification,
} from '../types'

const apiBase = import.meta.env.VITE_API_URL ?? '/api/v1'

async function request<T>(path: string): Promise<T> {
  const token = window.localStorage.getItem('fais_access_token')
  const response = await fetch(`${apiBase}${path}`, {
    headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}
async function mutate<T>(path: string, method: string, body?: unknown): Promise<T> {
  const token = window.localStorage.getItem('fais_access_token')
  const response = await fetch(`${apiBase}${path}`, {
    method,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>
}

async function optionalRequest<T>(path: string): Promise<T | null> {
  const response = await fetch(`${apiBase}${path}`, { headers: { Accept: 'application/json' } })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

export const api = {
  overview: () => request<Overview>('/overview'),
  competitions: (limit = 12) => request<Competition[]>(`/competitions?limit=${limit}`),
  matches: (filters: { limit?: number; status?: string; team_id?: number } = {}) => {
    const query = new URLSearchParams()
    query.set('limit', String(filters.limit ?? 25))
    if (filters.status) query.set('status', filters.status)
    if (filters.team_id) query.set('team_id', String(filters.team_id))
    return request<Match[]>(`/matches?${query}`)
  },
  match: (id: number) => request<Match>(`/matches/${id}`),
  prediction: (id: number) => optionalRequest<Prediction>(`/matches/${id}/prediction`),
  teams: (search = '', limit = 100) =>
    request<TeamSummary[]>(`/teams?search=${encodeURIComponent(search)}&limit=${limit}`),
  team: (id: number) => request<TeamDetail>(`/teams/${id}`),
  qualityIssues: (limit = 100) => request<QualityIssue[]>(`/quality/issues?limit=${limit}`),
  models: () => request<ModelVersion[]>('/models'),
  backtests: () => request<Backtest[]>('/backtests'),
  register: (email: string, password: string, display_name: string) =>
    mutate<{ user: User; access_token: string }>('/auth/register', 'POST', { email, password, display_name }),
  login: (email: string, password: string) =>
    mutate<{ access_token: string }>('/auth/token', 'POST', { email, password }),
  me: () => request<User>('/auth/me'),
  favorites: () => request<Favorite[]>('/favorites'),
  notifications: () => request<Notification[]>('/notifications'),
  favoriteTeam: (team_id: number) => mutate<Favorite>('/favorites', 'POST', { team_id }),
  favoriteMatch: (match_id: number) => mutate<Favorite>('/favorites', 'POST', { match_id }),
  addAlert: (match_id: number, event_type: string) =>
    mutate('/alerts', 'POST', { match_id, event_type }),
}
