"use client";

import { useQuery } from "@tanstack/react-query";
import { Users, DollarSign, TrendingUp, BarChart3 } from "lucide-react";
import {
  getRecommendationReport,
  getContentRankings,
  getAttributionWindow,
} from "@/lib/api";
import {
  LiftChart,
  RecommendationCard,
  StatsCard,
  WeeklyPlan,
  ConfounderAlert,
} from "@/components";

// Demo creator ID - replace with dynamic routing in production
const DEMO_CREATOR_ID = "8b80261c-e62d-4744-b017-f3d5d057199b";

export default function Dashboard() {
  const {
    data: report,
    isLoading: reportLoading,
    error: reportError,
  } = useQuery({
    queryKey: ["recommendations", DEMO_CREATOR_ID],
    queryFn: () => getRecommendationReport(DEMO_CREATOR_ID, 30),
  });

  const { data: rankings, isLoading: rankingsLoading } = useQuery({
    queryKey: ["rankings", DEMO_CREATOR_ID],
    queryFn: () => getContentRankings(DEMO_CREATOR_ID, 30),
  });

  const { data: attribution } = useQuery({
    queryKey: ["attribution", DEMO_CREATOR_ID],
    queryFn: () => getAttributionWindow(DEMO_CREATOR_ID, 7),
  });

  if (reportLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (reportError) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <h2 className="text-lg font-semibold text-red-800">Error Loading Data</h2>
          <p className="mt-2 text-sm text-red-600">
            Could not connect to the API. Make sure the backend is running on port 8080.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">FunnelLens</h1>
              <p className="text-sm text-gray-500">Content Performance Dashboard</p>
            </div>
            <div className="flex items-center gap-4">
              <select className="bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm">
                <option>Last 30 days</option>
                <option>Last 14 days</option>
                <option>Last 7 days</option>
              </select>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Confounder Alert */}
        {report?.has_confounders && report.confounder_warning && (
          <div className="mb-6">
            <ConfounderAlert
              warning={report.confounder_warning}
              confounders={attribution?.confounders}
            />
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatsCard
            title="Total Subscribers"
            value={report?.total_subs ?? 0}
            subtitle={`in ${report?.period_days ?? 0} days`}
            icon={<Users className="w-6 h-6 text-indigo-600" />}
          />
          <StatsCard
            title="Total Revenue"
            value={`$${(report?.total_revenue ?? 0).toLocaleString()}`}
            subtitle="attributed revenue"
            icon={<DollarSign className="w-6 h-6 text-green-600" />}
          />
          <StatsCard
            title="Subscriber Lift"
            value={`${attribution?.subs_lift_pct?.toFixed(0) ?? 0}%`}
            subtitle="vs baseline"
            icon={<TrendingUp className="w-6 h-6 text-blue-600" />}
            trend={
              attribution?.subs_lift_pct
                ? { value: attribution.subs_lift_pct, label: "lift" }
                : undefined
            }
          />
          <StatsCard
            title="Top Performer"
            value={report?.top_performer ?? "—"}
            subtitle={report?.top_performer ? "highest lift content type" : "needs more data"}
            icon={<BarChart3 className="w-6 h-6 text-purple-600" />}
            variant={report?.top_performer ? "success" : "default"}
          />
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column - Chart & Plan */}
          <div className="lg:col-span-2 space-y-8">
            {/* Lift Chart */}
            {rankings && !rankingsLoading && (
              <LiftChart rankings={rankings.rankings} />
            )}

            {/* Data Quality Notes */}
            {report?.data_quality_notes && report.data_quality_notes.length > 0 && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <h4 className="font-semibold text-blue-800 mb-2">Data Quality Notes</h4>
                <ul className="space-y-1">
                  {report.data_quality_notes.map((note, i) => (
                    <li key={i} className="text-sm text-blue-700">
                      {note}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Right Column - Weekly Plan */}
          <div>
            {report?.weekly_plan && <WeeklyPlan plan={report.weekly_plan} />}
          </div>
        </div>

        {/* Recommendations Section */}
        <div className="mt-8">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            Content Recommendations
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {report?.recommendations.map((rec, i) => (
              <RecommendationCard key={i} recommendation={rec} />
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <p className="text-sm text-gray-500 text-center">
            FunnelLens v0.1.0 — Analytics for Creator Agencies
          </p>
        </div>
      </footer>
    </div>
  );
}
