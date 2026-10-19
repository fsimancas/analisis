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
