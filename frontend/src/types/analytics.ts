export interface AnalyticsDashboardMetrics {
  from_date: string;
  to_date: string;
  total_tickets: number;
  bot_resolved_percent: number;
  bot_resolved_tickets: number;
  avg_first_response_time_sec: number;
  avg_handling_time_sec: number;
  client_csat: number;
  adjusted_csat: number;
  avg_ai_politeness_score: number;
  avg_ai_completeness_score: number;
  active_incidents_count: number;
}

export type IncidentType = 'portal_downtime' | 'crypto_plugin' | 'api_error';
export type IncidentStatus = 'open' | 'in_review' | 'resolved';

export interface SystemIncident {
  id: string;
  ticket_id: string;
  incident_type: IncidentType | string;
  description: string;
  status: IncidentStatus | string;
  created_at: string;
  resolved_at?: string | null;
  error_code?: string;
  llm_verdict?: string;
  raw_score?: number;
  adjusted_score?: number;
  dialog_excerpt?: string;
  operator_name?: string;
}

export interface OperatorDailyMetric {
  operator_id: string;
  operator_name: string;
  line_code: string;
  metric_date: string;
  total_tickets_handled: number;
  avg_first_response_time_sec?: number | null;
  avg_handling_time_sec?: number | null;
  avg_client_csat?: number | null;
  avg_adjusted_csat?: number | null;
  avg_ai_quality_score?: number | null;
}

export interface DeflectionTrendPoint {
  dayLabel: string;
  rate: number;
  botCount: number;
  totalCount: number;
}

export interface CategoryBreakdown {
  label: string;
  count: number;
  share: number;
  color: string;
}

export interface SlaTimelinePoint {
  timeLabel: string;
  frtSec: number;
  slaTargetSec: number;
  ahtSec: number;
}

export interface CsatDistributionPoint {
  stars: number;
  rawCount: number;
  adjustedCount: number;
  excludedCount: number;
}

