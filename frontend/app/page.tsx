"use client";

import { useState } from "react";
import { ComplianceGraph } from "@/components/ComplianceGraph";
import { UploadSection } from "@/components/UploadSection";
import { FilterPanel } from "@/components/FilterPanel";
import { ComplianceSummary } from "@/components/ComplianceSummary";

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  controls: string[];
}

export interface GraphEdge {
  from: string;
  to: string;
  protocol: string;
}

export interface ComplianceScore {
  NIS2: number;
  DORA: number;
  RGPD: number;
  AI_Act: number;
  CRA: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  compliance_scores_by_node: Record<string, ComplianceScore>;
}

export type Regulation = "NIS2" | "DORA" | "RGPD" | "AI_Act" | "CRA";

export default function Home() {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [selectedRegulations, setSelectedRegulations] = useState<Regulation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileUpload = async (file: File) => {
    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("/api/analyze-infrastructure-graph", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || "Failed to extract graph");
      }

      setGraphData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      console.error("Upload error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRegulationToggle = (regulation: Regulation) => {
    setSelectedRegulations((prev) =>
      prev.includes(regulation)
        ? prev.filter((r) => r !== regulation)
        : [...prev, regulation]
    );
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-8">
      <div className="max-w-7xl mx-auto">
        <header className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">
            Interactive Compliance Graph
          </h1>
          <p className="text-slate-400">
            Upload your DAT document to visualize infrastructure compliance
          </p>
        </header>

        {!graphData ? (
          <UploadSection
            onFileUpload={handleFileUpload}
            loading={loading}
            error={error}
          />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <FilterPanel
                selectedRegulations={selectedRegulations}
                onRegulationToggle={handleRegulationToggle}
              />
              <ComplianceSummary graphData={graphData} />
              <button
                onClick={() => setGraphData(null)}
                className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
              >
                Upload New Document
              </button>
            </div>

            <div className="lg:col-span-3">
              <ComplianceGraph
                graphData={graphData}
                selectedRegulations={selectedRegulations}
              />
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
