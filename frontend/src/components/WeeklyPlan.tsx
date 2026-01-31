"use client";

import { Calendar } from "lucide-react";
import type { WeeklyPlan as WeeklyPlanType } from "@/lib/api";

interface WeeklyPlanProps {
  plan: WeeklyPlanType;
}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  storytime: "Storytime",
  grwm: "GRWM",
  thirst_trap: "Thirst Trap",
  behind_scenes: "Behind Scenes",
  money_talk: "Money Talk",
  other: "Other",
};

const CONTENT_TYPE_COLORS: Record<string, string> = {
  storytime: "bg-purple-500",
  grwm: "bg-pink-500",
  thirst_trap: "bg-red-500",
  behind_scenes: "bg-blue-500",
  money_talk: "bg-green-500",
  other: "bg-gray-500",
};

export function WeeklyPlan({ plan }: WeeklyPlanProps) {
  const hasBreakdown = Object.keys(plan.breakdown).length > 0;

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center gap-3 mb-4">
        <Calendar className="w-5 h-5 text-gray-600" />
        <h3 className="text-lg font-semibold text-gray-900">Weekly Plan</h3>
      </div>

      <div className="mb-4">
        <div className="text-3xl font-bold text-gray-900">
          {plan.total_posts} posts
        </div>
        <div className="text-sm text-gray-500">suggested per week</div>
      </div>

      {hasBreakdown ? (
        <>
          <div className="space-y-3">
            {Object.entries(plan.breakdown)
              .sort(([, a], [, b]) => b - a)
              .map(([contentType, count]) => {
                const label = CONTENT_TYPE_LABELS[contentType] || contentType;
                const color = CONTENT_TYPE_COLORS[contentType] || "bg-gray-500";
                const percentage = (count / plan.total_posts) * 100;

                return (
                  <div key={contentType}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-gray-700">{label}</span>
                      <span className="font-medium text-gray-900">
                        {count} posts
                      </span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${color} rounded-full`}
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                );
              })}
          </div>
        </>
      ) : (
        <div className="text-sm text-gray-500 italic">
          No specific breakdown available
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-gray-100">
        <p className="text-sm text-gray-600">{plan.rationale}</p>
      </div>
    </div>
  );
}
