export interface Overview {
  counts: {
    countries: number
    competitions: number
    teams: number
    matches: number
    predictions: number
  }
  matches_by_status: Record<string, number>
  open_quality_issues: number
}
export interface Competition {
  id: number
  slug: string
  name: string
  sport: string
  active: number
  country: string | null
  match_count: number
}

export interface Match {
  id: number
  competition_id: number
  competition: string
  home_team: string
  away_team: string
  kickoff_utc: string | null
  kickoff_date: string | null
  kickoff_precision: 'MINUTE' | 'DATE' | 'UNKNOWN'
  kickoff_raw: string | null
  round_name: string | null
  status: string
  home_score: number | null
  away_score: number | null
}

export interface TeamSummary {
  id: number
  name: string
  country: string | null
  match_count: number
}

export interface TeamDetail extends TeamSummary {
  played: number
  wins: number
  draws: number
  losses: number
  goals_for: number
  goals_against: number
  form: Array<'W' | 'D' | 'L'>
}

export interface QualityIssue {
  id: number
  entity_type: string
  entity_id: string | null
  code: string
  severity: string
  context: Record<string, unknown> | null
  detected_at: string
  resolved_at: string | null
}

export interface ModelVersion {
  id: number
  name: string
  algorithm: string
  version: string
  feature_version: string
  active: boolean
  metrics: Record<string, unknown>
  created_at: string
}

export interface Backtest {
  id: string
  model: string
  version: string
  started_at: string
  finished_at: string | null
  status: string
  metrics: {
    evaluated?: number
    accuracy?: number
    log_loss?: number
    brier_score?: number
    expected_calibration_error?: number
  } | null
}

export interface Prediction {
  id: number
  match_id: number
  model_version: string
  payload: {
    expected_goals: { home: number; away: number }
    markets: {
      one_x_two: { home: number; draw: number; away: number }
      goals: Record<string, number>
      btts: { yes: number; no: number }
    }
  }
}

export interface User {
  id: number
  email: string
  display_name: string
  role: 'USER' | 'ANALYST' | 'ADMIN'
  active: number
  created_at: string
}

export interface Favorite {
  id: number
  user_id: number
  match_id: number | null
  team_id: number | null
  created_at: string
}

export interface Notification {
  id: number
  alert_id: number
  event_key: string
  title: string
  payload: Record<string, unknown>
  created_at: string
  read_at: string | null
}

export type AdminSummary = Record<string, number>

export interface AdminCountry {
  id: number
  slug: string
  name: string
  created_at: string
}

export interface AdminCompetition extends Competition {
  country_id: number
  gender: string | null
  tier: string | null
}

export interface AdminTeam {
  id: number
  canonical_name: string
  normalized_name: string
  country_id: number
  country: string | null
}

export interface AdminJob {
  id: string
  job_type: string
  status: string
  payload: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
}

export interface AdminChannel {
  id: number
  name: string
  webhook_url: string
  enabled: number
}

export interface AdminScraper {
  id: number
  name: string
  country_slug: string
  competition_slug: string
  provider_code: 'flashscore' | 'fotmob' | 'betplay'
  ingestion_kind: 'MATCHES' | 'ODDS' | 'DETAILS'
  enabled: number
}

export interface CompetitionPermission {
  competition_id: number
  competition: string
  country: string | null
  granted_by: number | null
  granted_at: string
}

export interface OddsValue {
  match_id: number
  prediction_id: number
  model_version: string
  markets: Array<{
    id: number
    provider: string
    market_key: string
    selection_key: string
    line: number | null
    decimal_odd: number
    implied_probability: number
    fair_implied_probability: number
    overround: number
    model_probability: number | null
    expected_value: number | null
    edge: number | null
  }>
}

export interface MonteCarloResult {
  version: string
  iterations: number
  seed: number
  expected_goals: { home: number; away: number }
  one_x_two: { home: number; draw: number; away: number }
  markets: Record<string, number>
  top_scorelines: Array<{ home: number; away: number; probability: number }>
}

export interface AnalysisRun {
  id: string
  match_id: number
  analysis_type: string
  status: string
  parameters: Record<string, unknown>
  result: MonteCarloResult | null
  created_at: string
}

export interface AnalystWorkbook {
  id: string
  match_id: number | null
  title: string
  notes: string
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface MatchDetails {
  match: Match & { home_team_id: number; away_team_id: number }
  lineups: Array<Record<string, unknown> & { id: number; team: string; players: Array<Record<string, unknown>> }>
  referees: Array<{ id: number; name: string; category: string | null; role: string }>
  events: Array<Record<string, unknown>>
  team_statistics: Array<Record<string, unknown>>
}

export interface AuditEntry {
  id: number
  actor_email: string | null
  action: string
  entity_type: string
  entity_id: string | null
  before_payload: Record<string, unknown> | null
  after_payload: Record<string, unknown> | null
  remote_address: string | null
  created_at: string
}

export interface DeploymentPreflight {
  ready: boolean
  environment: string
  domain: string | null
  database: string
  redis: string
  issues: string[]
  systemd_activation_required: boolean
  dns_verification_required: boolean
}
