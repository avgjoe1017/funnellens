"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import type { ContentRanking } from "@/lib/api";

interface LiftChartProps {
  rankings: ContentRanking[];
}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  storytime: "Storytime",
  grwm: "GRWM",
  thirst_trap: "Thirst Trap",
  behind_scenes: "Behind Scenes",
  money_talk: "Money Talk",
  other: "Other",
};

export function LiftChart({ rankings }: LiftChartProps) {
  const data = rankings.map((r) => ({
    name: CONTENT_TYPE_LABELS[r.content_type] || r.content_type,
    lift: r.lift_pct ?? 0,
    tier: r.tier,
    confidence: r.confidence_score,
  }));

  const getBarColor = (lift: number, tier: string) => {
    if (tier === "confident") {
      return lift >= 0 ? "#22c55e" : "#ef4444"; // green-500 / red-500
    }
    return lift >= 0 ? "#86efac" : "#fca5a5"; // green-300 / red-300 (lighter for hypothesis)
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">
        Content Type Performance (Lift %)
      </h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 80, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} />
            <XAxis
              type="number"
              domain={["dataMin - 10", "dataMax + 10"]}
              tickFormatter={(value) => `${value}%`}
            />
            <YAxis type="category" dataKey="name" width={75} />
            <Tooltip
              formatter={(value: number) => [`${value.toFixed(1)}%`, "Lift"]}
              labelFormatter={(label) => label}
            />
            <ReferenceLine x={0} stroke="#666" />
            <Bar dataKey="lift" radius={[0, 4, 4, 0]}>
              {data.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={getBarColor(entry.lift, entry.tier)}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 flex gap-4 text-sm text-gray-600">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-green-500" />
          <span>Confident Positive</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-green-300" />
          <span>Hypothesis Positive</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-red-500" />
          <span>Confident Negative</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-red-300" />
          <span>Hypothesis Negative</span>
        </div>
      </div>
    </div>
  );
}
