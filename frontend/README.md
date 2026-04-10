# Interactive Compliance Graph Visualization - Frontend

Next.js application for visualizing infrastructure compliance as an interactive graph.

## Quick Start

### Install Dependencies

```bash
npm install
```

### Development Mode

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Production Build

```bash
npm run build
npm start
```

## Features

- **Interactive Graph Visualization**: Force-directed graph using react-force-graph-2d
- **Compliance Color-Coding**:
  - 🔴 Red: <60% compliant
  - 🟡 Yellow: 60-90% compliant
  - 🟢 Green: >90% compliant
- **Filter by Regulation**: NIS2, DORA, RGPD, AI Act, CRA
- **Node Details Modal**: Click any node to see:
  - Compliance score per regulation
  - Detected security controls
  - Identified gaps
  - Remediation recommendations
- **Glassmorphism UI**: Modern, portfolio-quality design

## Architecture

### Components

- `app/page.tsx`: Main page with upload and graph rendering
- `components/UploadSection.tsx`: File upload interface
- `components/ComplianceGraph.tsx`: Force-directed graph visualization
- `components/NodeDetailsModal.tsx`: Detailed compliance information
- `components/FilterPanel.tsx`: Regulation filter controls
- `components/ComplianceSummary.tsx`: Overall compliance scores

### API Integration

The frontend communicates with the FastAPI backend via `/api/analyze-infrastructure-graph` endpoint:

```typescript
POST /api/analyze-infrastructure-graph
Content-Type: multipart/form-data

file: <DAT document (.pdf or .docx)>

Response:
{
  success: boolean,
  nodes: Array<{ id, name, type, controls }>,
  edges: Array<{ from, to, protocol }>,
  compliance_scores_by_node: Record<nodeId, { NIS2, DORA, RGPD, AI_Act, CRA }>
}
```

The backend is proxied via `next.config.js` rewrites for local development.

## Dependencies

### Core
- **Next.js 15**: React framework
- **React 19**: UI library
- **TypeScript**: Type safety

### Graph Visualization
- **react-force-graph-2d**: Force-directed graph layout

### UI Components
- **Radix UI**: Accessible component primitives
- **Tailwind CSS**: Utility-first styling
- **Lucide React**: Icon library

## Environment Variables

Create `.env.local` (optional):

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

If not set, the app uses Next.js rewrites (configured in `next.config.js`).

## Styling

The app uses a dark mode theme with:
- **Glassmorphism**: Frosted glass effects
- **Color Palette**: Slate/Blue theme
- **Animations**: Smooth transitions
- **Responsive**: Mobile-friendly layout

## Performance

- Target <100ms for filter operations on 100-node graphs
- Canvas rendering for efficient graph visualization
- Compliance scores cached in React state

## Troubleshooting

### Graph won't render

Make sure the dynamic import is working:
```typescript
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});
```

### API calls fail

1. Check backend is running: `curl http://localhost:8000/health`
2. Verify `next.config.js` rewrites are configured
3. Check browser console for CORS errors

### Build errors

```bash
rm -rf .next node_modules
npm install
npm run build
```

## Deployment

See `DEPLOYMENT-GRAPH-VIZ.md` in the project root for production deployment instructions.

## License

Part of the RAG Chatbot Production project.
