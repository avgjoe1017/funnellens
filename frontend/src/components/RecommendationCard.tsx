"use client";

import { TrendingUp, TrendingDown, Minus, FlaskConical, AlertTriangle } from "lucide-react";
import type { ContentRecommendation } from "@/lib/api";

interface RecommendationCardProps {
  recommendation: ContentRecommendation;
}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  storytime: "Storytime",
  grwm: "GRWM",
  thirst_trap: "Thirst Trap",
  behind_scenes: "Behind Scenes",
  money_talk: "Money Talk",
  other: "Other",
};

const ACTION_CONFIG = {
  increase: {
    icon: TrendingUp,
    color: "text-green-600",
    bgColor: "bg-green-50",
    borderColor: "border-green-200",
    label: "Increase",
  },
  decrease: {
    icon: TrendingDown,
    color: "text-red-600",
    bgColor: "bg-red-50",
    borderColor: "border-red-200",
    label: "Decrease",
  },
  maintain: {
    icon: Minus,
    color: "text-gray-600",
    bgColor: "bg-gray-50",
    borderColor: "border-gray-200",
    label: "Maintain",
  },
  test: {
    icon: FlaskConical,
    color: "text-amber-600",
    bgColor: "bg-amber-50",
    borderColor: "border-amber-200",
    label: "Test",
  },
};

export function RecommendationCard({ recommendation }: RecommendationCardProps) {
  const config = ACTION_CONFIG[recommendation.action as keyof typeof ACTION_CONFIG] || ACTION_CONFIG.test;
  const Icon = config.icon;
  const label = CONTENT_TYPE_LABELS[recommendation.content_type] || recommendation.content_type;

  return (
    <div className={`rounded-lg border ${config.borderColor} ${config.bgColor} p-4`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-full ${config.bgColor}`}>
            <Icon className={`w-5 h-5 ${config.color}`} />
          </div>
          <div>
            <h4 className="font-semibold text-gray-900">{label}</h4>
            <span className={`text-sm ${config.color} font-medium`}>
              {config.label}
            </span>
          </div>
        </div>
        <div className="text-right">
          {recommendation.lift_pct !== null && (
            <div className={`text-lg font-bold ${recommendation.lift_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
              {recommendation.lift_pct >= 0 ? "+" : ""}
              {recommendation.lift_pct.toFixed(0)}%
            </div>
          )}
          <div className="text-xs text-gray-500">
            {recommendation.tier === "confident" ? (
              <span className="text-green-600">Confident</span>
            ) : (
              <span className="text-amber-600">Hypothesis</span>
            )}
          </div>
        </div>
      </div>

      <p className="mt-3 text-sm text-gray-700">{recommendation.reasoning}</p>

      {recommendation.suggested_posts_per_week !== null && (
        <div className="mt-3 text-sm text-gray-600">
          <span className="font-medium">Suggested:</span>{" "}
          {recommendation.current_posts_per_week.toFixed(0)} →{" "}
          {recommendation.suggested_posts_per_week.toFixed(0)} posts/week
        </div>
      )}

      {recommendation.caveats.length > 0 && (
        <div className="mt-3 space-y-1">
          {recommendation.caveats.map((caveat, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-gray-500">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{caveat}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
