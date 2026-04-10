"use client";

import { X, Shield, AlertTriangle, CheckCircle } from "lucide-react";
import type { ComplianceScore } from "@/app/page";

interface NodeDetailsModalProps {
  node: {
    id: string;
    name: string;
    type: string;
    controls: string[];
    complianceScore: number;
  };
  complianceScores: ComplianceScore;
  onClose: () => void;
}

const regulationDetails: Record<
  keyof ComplianceScore,
  { label: string; color: string }
> = {
  NIS2: { label: "NIS2", color: "text-blue-400" },
  DORA: { label: "DORA", color: "text-purple-400" },
  RGPD: { label: "RGPD", color: "text-green-400" },
  AI_Act: { label: "AI Act", color: "text-orange-400" },
  CRA: { label: "CRA", color: "text-pink-400" },
};

const getGapsByRegulation = (
  regulation: keyof ComplianceScore,
  score: number,
  controls: string[]
): string[] => {
  const gaps: string[] = [];

  if (regulation === "NIS2") {
    if (!controls.some((c) => c.includes("TLS") || c.includes("encryption"))) {
      gaps.push("Missing encryption/TLS implementation");
    }
    if (!controls.some((c) => c.includes("monitoring") || c.includes("logging"))) {
      gaps.push("No monitoring or SIEM integration");
    }
    if (!controls.some((c) => c.includes("incident"))) {
      gaps.push("No 24h incident notification process");
    }
    if (!controls.some((c) => c.includes("backup"))) {
      gaps.push("Missing backup/disaster recovery plan");
    }
  } else if (regulation === "DORA") {
    if (!controls.some((c) => c.includes("resilience") || c.includes("testing"))) {
      gaps.push("No ICT resilience testing documented");
    }
    if (!controls.some((c) => c.includes("vendor") || c.includes("third_party"))) {
      gaps.push("Third-party risk management not implemented");
    }
  } else if (regulation === "RGPD") {
    if (!controls.some((c) => c.includes("IAM") || c.includes("MFA"))) {
      gaps.push("Missing access control/IAM implementation");
    }
    if (!controls.some((c) => c.includes("audit") || c.includes("log"))) {
      gaps.push("No audit logging for personal data access");
    }
  } else if (regulation === "AI_Act") {
    if (!controls.some((c) => c.includes("documentation") || c.includes("transparency"))) {
      gaps.push("Missing AI model documentation/transparency");
    }
    if (!controls.some((c) => c.includes("bias") || c.includes("fairness"))) {
      gaps.push("No bias monitoring or fairness testing");
    }
  } else if (regulation === "CRA") {
    if (!controls.some((c) => c.includes("vulnerability") || c.includes("patch"))) {
      gaps.push("No vulnerability management process");
    }
    if (!controls.some((c) => c.includes("SBOM") || c.includes("supply_chain"))) {
      gaps.push("Missing SBOM or supply chain security");
    }
  }

  return gaps;
};

export function NodeDetailsModal({
  node,
  complianceScores,
  onClose,
}: NodeDetailsModalProps) {
  const avgScore =
    Object.values(complianceScores).reduce((sum, score) => sum + score, 0) / 5;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="glass max-w-2xl w-full max-h-[90vh] overflow-y-auto rounded-2xl p-6">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white mb-1">{node.name}</h2>
            <p className="text-slate-400">
              Type: <span className="text-blue-400">{node.type}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>

        <div className="mb-6 p-4 glass-light rounded-xl">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-slate-300">
              Overall Compliance
            </span>
            <span className="text-2xl font-bold text-white">
              {avgScore.toFixed(0)}%
            </span>
          </div>
          <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all ${
                avgScore >= 90
                  ? "bg-green-500"
                  : avgScore >= 60
                  ? "bg-yellow-500"
                  : "bg-red-500"
              }`}
              style={{ width: `${avgScore}%` }}
            />
          </div>
        </div>

        <div className="mb-6">
          <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
            <Shield className="h-5 w-5 text-blue-400" />
            Security Controls
          </h3>
          {node.controls.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {node.controls.map((control, idx) => (
                <span
                  key={idx}
                  className="px-3 py-1 bg-blue-900/30 border border-blue-500/30 text-blue-300 rounded-full text-sm"
                >
                  {control}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-slate-400 text-sm">No controls detected</p>
          )}
        </div>

        <div>
          <h3 className="text-lg font-semibold text-white mb-3">
            Compliance by Regulation
          </h3>
          <div className="space-y-4">
            {(Object.keys(complianceScores) as Array<keyof ComplianceScore>).map(
              (reg) => {
                const score = complianceScores[reg];
                const gaps = getGapsByRegulation(reg, score, node.controls);
                const details = regulationDetails[reg];

                return (
                  <div key={reg} className="glass-light rounded-xl p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className={`font-semibold ${details.color}`}>
                        {details.label}
                      </span>
                      <span className="text-white font-semibold">
                        {score.toFixed(0)}%
                      </span>
                    </div>

                    <div className="h-2 bg-slate-700 rounded-full overflow-hidden mb-3">
                      <div
                        className={`h-full transition-all ${
                          score >= 90
                            ? "bg-green-500"
                            : score >= 60
                            ? "bg-yellow-500"
                            : "bg-red-500"
                        }`}
                        style={{ width: `${score}%` }}
                      />
                    </div>

                    {gaps.length > 0 ? (
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 text-sm text-slate-400">
                          <AlertTriangle className="h-4 w-4 text-yellow-500" />
                          <span>Gaps Identified:</span>
                        </div>
                        <ul className="ml-6 space-y-1">
                          {gaps.map((gap, idx) => (
                            <li
                              key={idx}
                              className="text-sm text-slate-300 list-disc"
                            >
                              {gap}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-sm text-green-400">
                        <CheckCircle className="h-4 w-4" />
                        <span>No major gaps identified</span>
                      </div>
                    )}
                  </div>
                );
              }
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
