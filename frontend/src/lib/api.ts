/**
 * FunnelLens API client
 */

import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8080";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Types
export interface BaselineResponse {
  subs_per_day: number;
  rev_per_day: number;
  data_days: number;
  is_default: boolean;
}

export interface ConfidenceResponse {
  score: number;
  level: string;
  reasons: string[];
  min_events_met: boolean;
}

export interface ContentTypeMetrics {
  views_delta: number;
  posts_with_views: number;
  attributed_subs: number | null;
  subs_per_1k_views: number | null;
  lift_pct: number | null;
  credit_weight: number;
  confidence: ConfidenceResponse | null;
  tier: string | null;
}

export interface AttributionWindowResponse {
  creator_id: string;
  window_start: string;
  window_end: string;
  window_hours: number;
  baseline: BaselineResponse;
  expected_subs: number;
  actual_subs: number;
  subs_lift_pct: number;
  expected_revenue: number;
  actual_revenue: number;
  revenue_lift_pct: number;
  content_type_deltas: Record<string, ContentTypeMetrics>;
  credit_weights: Record<string, number>;
  total_delta_views: number;
  confounders: Array<{ event_type: string; description: string }>;
  confidence: ConfidenceResponse;
  recommendation_tier: string;
}

export interface ContentTypePerformanceResponse {
  creator_id: string;
  period_days: number;
  window_start: string;
  window_end: string;
  total_subs: number;
  total_views: number;
  has_confounders: boolean;
  confounders: Array<{ event_type: string; description: string }>;
  content_types: Record<string, ContentTypeMetrics>;
}

export interface ContentRecommendation {
  content_type: string;
  action: string;
  tier: string;
  lift_pct: number | null;
  confidence_score: number;
  current_posts_per_week: number;
  suggested_posts_per_week: number | null;
  reasoning: string;
  caveats: string[];
}

export interface WeeklyPlan {
  total_posts: number;
  breakdown: Record<string, number>;
  rationale: string;
}

export interface RecommendationReport {
  creator_id: string;
  period_days: number;
  total_subs: number;
  total_revenue: number;
  has_confounders: boolean;
  confounder_warning: string | null;
  recommendations: ContentRecommendation[];
  weekly_plan: WeeklyPlan | null;
  top_performer: string | null;
  underperformer: string | null;
  data_quality_notes: string[];
}

export interface ContentRanking {
  rank: number;
  content_type: string;
  lift_pct: number | null;
  tier: string;
  confidence_score: number;
  posts_analyzed: number;
}

export interface RankingsResponse {
  creator_id: string;
  period_days: number;
  has_confounders: boolean;
  rankings: ContentRanking[];
}

// API Functions
export async function getHealth() {
  const response = await api.get("/health");
  return response.data;
}

export async function getBaseline(creatorId: string, lookbackDays = 14) {
  const response = await api.get<BaselineResponse>(
    `/api/v1/attribution/baseline/${creatorId}`,
    { params: { lookback_days: lookbackDays } }
  );
  return response.data;
}

export async function getAttributionWindow(creatorId: string, days = 7) {
  const response = await api.get<AttributionWindowResponse>(
    `/api/v1/attribution/window/${creatorId}`,
    { params: { days } }
  );
  return response.data;
}

export async function getContentTypePerformance(creatorId: string, days = 30) {
  const response = await api.get<ContentTypePerformanceResponse>(
    `/api/v1/attribution/performance/${creatorId}`,
    { params: { days } }
  );
  return response.data;
}

export async function getRecommendationReport(creatorId: string, days = 30) {
  const response = await api.get<RecommendationReport>(
    `/api/v1/recommendations/report/${creatorId}`,
    { params: { days } }
  );
  return response.data;
}

export async function getContentRankings(creatorId: string, days = 30) {
  const response = await api.get<RankingsResponse>(
    `/api/v1/recommendations/rankings/${creatorId}`,
    { params: { days } }
  );
  return response.data;
}
