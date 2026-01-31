"use client";

import type { ReactNode } from "react";

interface StatsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  trend?: {
    value: number;
    label: string;
  };
  variant?: "default" | "success" | "warning" | "danger";
}

const VARIANT_STYLES = {
  default: "bg-white border-gray-200",
  success: "bg-green-50 border-green-200",
  warning: "bg-amber-50 border-amber-200",
  danger: "bg-red-50 border-red-200",
};

export function StatsCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  variant = "default",
}: StatsCardProps) {
  return (
    <div className={`rounded-lg border p-6 ${VARIANT_STYLES[variant]}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="mt-2 text-3xl font-bold text-gray-900">{value}</p>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
          )}
          {trend && (
            <p
              className={`mt-2 text-sm font-medium ${
                trend.value >= 0 ? "text-green-600" : "text-red-600"
              }`}
            >
              {trend.value >= 0 ? "+" : ""}
              {trend.value.toFixed(1)}% {trend.label}
            </p>
          )}
        </div>
        {icon && (
          <div className="p-3 bg-gray-100 rounded-lg">{icon}</div>
        )}
      </div>
    </div>
  );
}
