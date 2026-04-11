"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import dynamic from "next/dynamic";
import type { GraphData, Regulation } from "@/app/page";
import { NodeDetailsModal } from "./NodeDetailsModal";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

interface ComplianceGraphProps {
  graphData: GraphData;
  selectedRegulations: Regulation[];
}

interface GraphNode {
  id: string;
  name: string;
  type: string;
  controls: string[];
  complianceScore: number;
}

interface GraphLink {
  source: string;
  target: string;
  protocol: string;
}

export function ComplianceGraph({
  graphData,
  selectedRegulations,
}: ComplianceGraphProps) {
  const graphRef = useRef<any>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    const updateDimensions = () => {
      setDimensions({
        width: window.innerWidth > 1024 ? window.innerWidth * 0.6 : window.innerWidth - 64,
        height: window.innerHeight - 200,
      });
    };

    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  const getNodeComplianceScore = (nodeId: string): number => {
    const scores = graphData.compliance_scores_by_node[nodeId];
    if (!scores) return 0;

    if (selectedRegulations.length === 0) {
      const allScores = Object.values(scores);
      return allScores.reduce((sum, score) => sum + score, 0) / allScores.length;
    }

    const selectedScores = selectedRegulations.map((reg) => scores[reg]);
    return selectedScores.reduce((sum, score) => sum + score, 0) / selectedScores.length;
  };

  const getNodeColor = (score: number): string => {
    if (score < 60) return "#ef4444"; // Red
    if (score < 90) return "#eab308"; // Yellow
    return "#22c55e"; // Green
  };

  const { filteredNodes, filteredLinks } = useMemo(() => {
    let nodes = graphData.nodes.map((node) => ({
      ...node,
      complianceScore: getNodeComplianceScore(node.id),
    }));

    if (selectedRegulations.length > 0) {
      nodes = nodes.filter((node) => node.complianceScore < 100);
    }

    const nodeIds = new Set(nodes.map((n) => n.id));
    const links = graphData.edges
      .filter((edge) => nodeIds.has(edge.from_) && nodeIds.has(edge.to))
      .map((edge) => ({
        source: edge.from_,
        target: edge.to,
        protocol: edge.protocol,
      }));

    console.log("Graph Debug:", {
      totalNodes: nodes.length,
      totalEdges: graphData.edges.length,
      filteredLinks: links.length,
      nodeIds: Array.from(nodeIds),
      edges: graphData.edges,
      links: links,
    });

    return { filteredNodes: nodes, filteredLinks: links };
  }, [graphData, selectedRegulations]);

  const handleNodeClick = (node: any) => {
    setSelectedNode(node);
  };

  return (
    <div className="glass rounded-xl p-6 relative">
      <div className="mb-4">
        <h2 className="text-2xl font-bold text-white mb-2">
          Infrastructure Compliance Map
        </h2>
        <p className="text-slate-400 text-sm">
          Click on any node to view compliance details
        </p>
      </div>

      <div
        className="bg-slate-900/50 rounded-lg overflow-hidden border border-slate-700"
        style={{ width: dimensions.width, height: dimensions.height }}
      >
        <ForceGraph2D
          ref={graphRef}
          graphData={{
            nodes: filteredNodes,
            links: filteredLinks,
          }}
          width={dimensions.width}
          height={dimensions.height}
          nodeLabel={(node: any) => `${node.name} (${node.type})`}
          nodeColor={(node: any) => getNodeColor(node.complianceScore)}
          nodeRelSize={8}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const label = node.name;
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px Sans-Serif`;
            const textWidth = ctx.measureText(label).width;
            const bckgDimensions = [textWidth, fontSize].map((n) => n + fontSize * 0.4);

            ctx.fillStyle = getNodeColor(node.complianceScore);
            ctx.beginPath();
            ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI, false);
            ctx.fill();

            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillStyle = "#e2e8f0";
            ctx.fillText(label, node.x, node.y + 20);
          }}
          linkColor={() => "#60a5fa"}
          linkWidth={3}
          linkDirectionalParticles={4}
          linkDirectionalParticleWidth={3}
          linkDirectionalParticleSpeed={0.008}
          linkLabel={(link: any) => link.protocol}
          onNodeClick={handleNodeClick}
          cooldownTicks={100}
          enableNodeDrag={false}
          enableZoomInteraction={true}
          enablePanInteraction={true}
        />
      </div>

      <div className="mt-4 flex items-center gap-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span className="text-slate-300">&gt;90% Compliant</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-yellow-500" />
          <span className="text-slate-300">60-90% Compliant</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <span className="text-slate-300">&lt;60% Compliant</span>
        </div>
      </div>

      {selectedNode && (
        <NodeDetailsModal
          node={selectedNode}
          complianceScores={graphData.compliance_scores_by_node[selectedNode.id]}
          onClose={() => setSelectedNode(null)}
        />
      )}
    </div>
  );
}
