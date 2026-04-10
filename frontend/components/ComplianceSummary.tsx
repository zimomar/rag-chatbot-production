"use client";

import { BarChart3 } from "lucide-react";
import type { GraphData, Regulation } from "@/app/page";

interface ComplianceSummaryProps {
  graphData: GraphData;
}

const regulations: { name: Regulation; label: string; color: string }[] = [
  { name: "NIS2", label: "NIS2", color: "bg-blue-500" },
  { name: "DORA", label: "DORA", color: "bg-purple-500" },
  { name: "RGPD", label: "RGPD", color: "bg-green-500" },
  { name: "AI_Act", label: "AI Act", color: "bg-orange-500" },
  { name: "CRA", label: "CRA", color: "bg-pink-500" },
];

export function ComplianceSummary({ graphData }: ComplianceSummaryProps) {
  const calculateAverageScore = (regulation: Regulation): number => {
    const scores = Object.values(graphData.compliance_scores_by_node).map(
      (score) => score[regulation]
    );
    return scores.reduce((sum, score) => sum + score, 0) / scores.length;
  };

  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="h-5 w-5 text-slate-400" />
        <h3 className="text-lg font-semibold text-white">
          Overall Compliance
        </h3>
      </div>

      <div className="space-y-4">
        {regulations.map((reg) => {
          const avgScore = calculateAverageScore(reg.name);
          return (
            <div key={reg.name}>
              <div className="flex justify-between mb-1">
                <span className="text-sm text-slate-300">{reg.label}</span>
                <span className="text-sm font-semibold text-white">
                  {avgScore.toFixed(0)}%
                </span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className={`h-full ${reg.color} transition-all duration-300`}
                  style={{ width: `${avgScore}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-4 border-t border-slate-700">
        <p className="text-xs text-slate-400">
          {graphData.nodes.length} components analyzed
        </p>
      </div>
    </div>
  );
}
