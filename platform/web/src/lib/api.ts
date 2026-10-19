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
  AdminChannel,
  AdminCompetition,
  AdminCountry,
  AdminJob,
  AdminScraper,
  AdminSummary,
  AdminTeam,
  AuditEntry,
  DeploymentPreflight,
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

async function upload<T>(path: string, body: FormData): Promise<T> {
  const token = window.localStorage.getItem('fais_access_token')
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body,
  })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

const destroy = <T>(path: string) => {
  const token = window.localStorage.getItem('fais_access_token')
  return fetch(`${apiBase}${path}`, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
      'X-Confirm-Action': 'delete',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  }).then((response) => {
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
    return undefined as T
  })
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
  adminSummary: () => request<AdminSummary>('/admin/summary'),
  adminCountries: () => request<AdminCountry[]>('/admin/countries'),
  saveCountry: (body: { id?: number; slug: string; name: string }) =>
    mutate<AdminCountry>(`/admin/countries${body.id ? `/${body.id}` : ''}`, body.id ? 'PUT' : 'POST', body),
  deleteCountry: (id: number) => destroy(`/admin/countries/${id}`),
  adminCompetitions: () => request<AdminCompetition[]>('/admin/competitions'),
  saveCompetition: (body: Record<string, unknown> & { id?: number }) =>
    mutate<AdminCompetition>(`/admin/competitions${body.id ? `/${body.id}` : ''}`, body.id ? 'PUT' : 'POST', body),
  deleteCompetition: (id: number) => destroy(`/admin/competitions/${id}`),
  adminTeams: (search = '') => request<AdminTeam[]>(`/admin/teams?search=${encodeURIComponent(search)}`),
  saveTeam: (body: { id?: number; country_id: number; canonical_name: string }) =>
    mutate<AdminTeam>(`/admin/teams${body.id ? `/${body.id}` : ''}`, body.id ? 'PUT' : 'POST', body),
  deleteTeam: (id: number) => destroy(`/admin/teams/${id}`),
  mergeTeams: (source_team_id: number, target_team_id: number) =>
    mutate('/admin/teams/merge', 'POST', { source_team_id, target_team_id }),
  aliases: (teamId: number) => request<Array<{ id: number; alias: string }>>(`/admin/teams/${teamId}/aliases`),
  addAlias: (teamId: number, alias: string) => mutate(`/admin/teams/${teamId}/aliases`, 'POST', { alias }),
  deleteAlias: (id: number) => destroy(`/admin/aliases/${id}`),
  adminMatches: () => request<Match[]>('/admin/matches'),
  saveMatch: (body: Record<string, unknown> & { id?: number }) =>
    mutate<Match>(`/admin/matches${body.id ? `/${body.id}` : ''}`, body.id ? 'PUT' : 'POST', body),
  deleteMatch: (id: number) => destroy(`/admin/matches/${id}`),
  resolveQuality: (id: number) => mutate(`/admin/quality/${id}/resolve`, 'POST'),
  adminUsers: () => request<User[]>('/admin/users'),
  updateUser: (id: number, role: User['role'], active: boolean) =>
    mutate<User>(`/admin/users/${id}`, 'PUT', { role, active }),
  channels: () => request<AdminChannel[]>('/admin/channels'),
  saveChannel: (id: number, body: { name: string; webhook_url: string; enabled: boolean }) =>
    mutate<AdminChannel>(`/admin/channels/${id}`, 'PUT', body),
  scrapers: () => request<AdminScraper[]>('/admin/scrapers'),
  saveScraper: (body: Record<string, unknown> & { id?: number }) =>
    mutate<AdminScraper>(`/admin/scrapers${body.id ? `/${body.id}` : ''}`, body.id ? 'PUT' : 'POST', body),
  deleteScraper: (id: number) => destroy(`/admin/scrapers/${id}`),
  runScrapers: () => mutate<AdminJob>('/admin/scrapers/run', 'POST'),
  adminJobs: () => request<AdminJob[]>('/admin/jobs'),
  runBacktest: () => mutate<AdminJob>('/admin/jobs/backtest', 'POST'),
  trainXgboost: () => mutate<AdminJob>('/admin/jobs/train-xgboost', 'POST'),
  uploadJson: (body: FormData) => upload('/admin/uploads/json', body),
  uploadSqlite: (body: FormData) => upload('/admin/uploads/sqlite', body),
  uploads: () => request<Array<Record<string, unknown>>>('/admin/uploads'),
  reviewModel: (id: number, decision: 'APPROVED' | 'REJECTED', notes = '') =>
    mutate(`/admin/models/${id}/review`, 'POST', { decision, notes }),
  audit: () => request<AuditEntry[]>('/admin/audit'),
  deploymentPreflight: () => request<DeploymentPreflight>('/admin/deployment/preflight'),
}
