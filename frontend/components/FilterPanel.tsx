"use client";

import { Filter } from "lucide-react";
import type { Regulation } from "@/app/page";

interface FilterPanelProps {
  selectedRegulations: Regulation[];
  onRegulationToggle: (regulation: Regulation) => void;
}

const regulations: { name: Regulation; label: string; color: string }[] = [
  { name: "NIS2", label: "NIS2", color: "text-blue-400" },
  { name: "DORA", label: "DORA", color: "text-purple-400" },
  { name: "RGPD", label: "RGPD", color: "text-green-400" },
  { name: "AI_Act", label: "AI Act", color: "text-orange-400" },
  { name: "CRA", label: "CRA", color: "text-pink-400" },
];

export function FilterPanel({
  selectedRegulations,
  onRegulationToggle,
}: FilterPanelProps) {
  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <Filter className="h-5 w-5 text-slate-400" />
        <h3 className="text-lg font-semibold text-white">Filter by Regulation</h3>
      </div>

      <div className="space-y-2">
        {regulations.map((reg) => (
          <label
            key={reg.name}
            className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-700/50 cursor-pointer transition-colors"
          >
            <input
              type="checkbox"
              checked={selectedRegulations.includes(reg.name)}
              onChange={() => onRegulationToggle(reg.name)}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500 focus:ring-offset-0"
            />
            <span className={`font-medium ${reg.color}`}>{reg.label}</span>
          </label>
        ))}
      </div>

      {selectedRegulations.length > 0 && (
        <p className="mt-4 text-sm text-slate-400">
          Showing gaps for {selectedRegulations.length} regulation
          {selectedRegulations.length > 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}
