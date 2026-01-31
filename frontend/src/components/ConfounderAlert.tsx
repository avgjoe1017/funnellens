"use client";

import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";

interface ConfounderAlertProps {
  warning: string;
  confounders?: Array<{ event_type: string; description: string }>;
}

export function ConfounderAlert({ warning, confounders }: ConfounderAlertProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="font-semibold text-amber-800">Confounder Alert</h4>
          <p className="mt-1 text-sm text-amber-700">{warning}</p>

          {confounders && confounders.length > 0 && (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-medium text-amber-800 uppercase tracking-wide">
                Detected Events:
              </p>
              {confounders.map((c, i) => (
                <div
                  key={i}
                  className="bg-amber-100 rounded px-3 py-2 text-sm text-amber-800"
                >
                  <span className="font-medium capitalize">
                    {c.event_type.replace("_", " ")}
                  </span>
                  {c.description && (
                    <span className="text-amber-700"> — {c.description}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-amber-600 hover:text-amber-800"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
