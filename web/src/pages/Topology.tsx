import { useRef, useMemo, useState, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { RefreshCw, ZoomIn, ZoomOut, LayoutTemplate, GitBranch, Maximize, RotateCcw } from 'lucide-react';
import { useTopology } from '../hooks/useTopology';
import { useDeviceEvents } from '../hooks';

function toColor(val: string): string {
  return /^\d/.test(val) ? `hsl(${val})` : val;
}

function drawNode(node: any, ctx: CanvasRenderingContext2D, globalScale: number) {
  const root = window.document.documentElement;
  const cs = getComputedStyle(root);
  const haloBg = toColor(cs.getPropertyValue('--canvas-halo-bg').trim());
  const haloFg = toColor(cs.getPropertyValue('--canvas-halo-fg').trim());
  const nodeStroke = toColor(cs.getPropertyValue('--canvas-node-stroke').trim());
  const canvasShadow = toColor(cs.getPropertyValue('--canvas-shadow').trim());

  const label = node.label || node.id;
  const fontSize = Math.max(10, 12 / globalScale);
  const nodeRadius = 7;

  const baseColor = node.node_type === 'router' ? '#da1e28'
    : node.node_type === 'firewall' ? '#f1c21b'
    : node.node_type === 'switch' ? '#0f62fe'
    : '#525252';
  const color = node.status === 'offline' ? '#8d8d8d' : baseColor;

  ctx.save();
  ctx.shadowColor = canvasShadow;
  ctx.shadowBlur = 4 / globalScale;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = 2 / globalScale;

  ctx.beginPath();
  ctx.arc(node.x, node.y, nodeRadius, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.restore();

  ctx.strokeStyle = nodeStroke;
  ctx.lineWidth = 1.8 / globalScale;
  ctx.stroke();

  ctx.font = `500 ${fontSize}px IBM Plex Sans, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  const textY = node.y + nodeRadius + 5 / globalScale;
  const textMetrics = ctx.measureText(label);
  const textWidth = textMetrics.width;
  const textHeight = fontSize;
  const pad = 3 / globalScale;

  ctx.fillStyle = haloBg;
  ctx.beginPath();
  ctx.roundRect(
    node.x - textWidth / 2 - pad,
    textY - pad,
    textWidth + pad * 2,
    textHeight + pad * 2,
    2 / globalScale,
  );
  ctx.fill();

  ctx.fillStyle = haloFg;
  ctx.fillText(label, node.x, textY);

  const statusColor = node.status === 'online' ? '#24a148'
    : node.status === 'offline' ? '#da1e28'
    : '#a8a8a8';
  ctx.beginPath();
  ctx.arc(node.x + nodeRadius - 1.5, node.y - nodeRadius + 1.5, 2.8, 0, 2 * Math.PI);
  ctx.fillStyle = statusColor;
  ctx.fill();
  ctx.strokeStyle = nodeStroke;
  ctx.lineWidth = 1 / globalScale;
  ctx.stroke();
}

export function Topology() {
  const { topology, isLoading, refresh, isStreaming, lastUpdate } = useTopology();
  useDeviceEvents();
  const graphRef = useRef<any>(null);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [hierarchical, setHierarchical] = useState(false);

  const handleFit = useCallback(() => {
    graphRef.current?.zoomToFit(400, 20);
  }, []);

  const handleReset = useCallback(() => {
    graphRef.current?.centerAt(0, 0, 400);
    graphRef.current?.zoom(1, 400);
  }, []);

  const graphData = useMemo(() => ({
    nodes: topology.nodes.map((n) => ({
      id: n.id,
      label: n.label || n.id,
      status: n.status,
      node_type: n.node_type,
      device_id: n.device_id,
      level: n.level ?? (n.node_type === 'firewall' ? 0 : n.node_type === 'router' ? 1 : n.node_type === 'switch' ? 3 : 2),
    })),
    links: topology.links.map((l) => ({
      source: l.source_id,
      target: l.target_id,
      source_port: l.source_port,
      target_port: l.target_port,
      status: l.status,
    })),
  }), [topology.nodes, topology.links]);

  const handleNodeClick = (node: any) => {
    setSelectedNode(node);
    graphRef.current?.centerOn(node, 400);
  };

  const handleLinkClick = (link: any) => {
    setSelectedNode({
      type: 'link',
      source: link.source.id || link.source,
      target: link.target.id || link.target,
      source_port: link.source_port,
      target_port: link.target_port,
      status: link.status,
    });
  };

  const linkColorFn = useCallback((_link: any) => {
    const cs = getComputedStyle(window.document.documentElement);
    const val = cs.getPropertyValue('--canvas-link-color').trim();
    return val ? toColor(val) : '#a8a8a8';
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-sm h-12 w-12 border-b-2 border-destructive mx-auto"></div>
          <p className="text-muted-foreground mt-4">Loading topology...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      <div className="bg-card border-b border-border px-6 py-4">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center space-x-3">
              <h1 className="text-2xl font-bold text-foreground">Network Topology</h1>
              <div
                className={`flex items-center space-x-1.5 px-2 py-1 rounded-sm text-xs font-medium ${
                  isStreaming
                    ? 'bg-badge-success-bg text-badge-success-fg'
                    : 'bg-badge-warning-bg text-badge-warning-fg'
                }`}
                title={isStreaming ? 'Receiving real-time updates' : 'Stream disconnected - attempting reconnect'}
              >
                <div className={`h-2 w-2 rounded-sm ${isStreaming ? 'bg-success animate-pulse' : 'bg-warning'}`} />
                <span className="hidden sm:inline">{isStreaming ? 'Live' : 'Connecting...'}</span>
              </div>
            </div>
            <p className="text-muted-foreground text-sm mt-1">
              {graphData.nodes.length} nodes • {graphData.links.length} links
              {lastUpdate && (
                <span className="ml-2">
                  • Updated {lastUpdate.toLocaleTimeString()}
                </span>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              onClick={handleFit}
              className="p-2 text-muted-foreground hover:bg-surface-hover rounded-sm"
              title="Fit to view"
            >
              <Maximize className="h-5 w-5" />
            </button>
            <button
              onClick={handleReset}
              className="p-2 text-muted-foreground hover:bg-surface-hover rounded-sm"
              title="Reset view"
            >
              <RotateCcw className="h-5 w-5" />
            </button>
            <button
              onClick={() => graphRef.current?.zoom(1.5, 400)}
              className="p-2 text-muted-foreground hover:bg-surface-hover rounded-sm"
              title="Zoom In"
            >
              <ZoomIn className="h-5 w-5" />
            </button>
            <button
              onClick={() => graphRef.current?.zoom(0.5, 400)}
              className="p-2 text-muted-foreground hover:bg-surface-hover rounded-sm"
              title="Zoom Out"
            >
              <ZoomOut className="h-5 w-5" />
            </button>
            <button
              onClick={() => setHierarchical((v) => !v)}
              className={`flex items-center space-x-2 px-3 py-2 rounded-sm text-sm font-medium ${
                hierarchical
                  ? 'bg-btn-accent text-btn-accent-foreground'
                  : 'text-muted-foreground hover:bg-surface-hover'
              }`}
              title={hierarchical ? 'Switch to force-directed layout' : 'Switch to hierarchical layout'}
            >
              {hierarchical ? <GitBranch className="h-4 w-4" /> : <LayoutTemplate className="h-4 w-4" />}
              <span className="hidden sm:inline">{hierarchical ? 'Hierarchy' : 'Force'}</span>
            </button>
            <button
              onClick={refresh}
              className="flex items-center space-x-2 px-4 py-2 bg-btn-accent text-btn-accent-foreground rounded-sm hover:bg-btn-accent-hover"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 flex">
        <div
          className="flex-1 relative"
          style={{
                backgroundColor: 'var(--grid-bg)',
                backgroundImage:
                  'radial-gradient(circle, var(--grid-dot) 1.2px, transparent 1.2px)',
            backgroundSize: '28px 28px',
          }}
        >
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            dagMode={hierarchical ? 'td' : undefined}
            dagLevelDistance={hierarchical ? 120 : undefined}
            nodeCanvasObject={drawNode}
            nodeRelSize={6}
            linkColor={linkColorFn}
            linkWidth={2}
            linkDirectionalArrowLength={hierarchical ? 6 : 0}
            nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D, _globalScale: number) => {
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI);
              ctx.fill();
            }}
            onNodeClick={handleNodeClick}
            onLinkClick={handleLinkClick}
            backgroundColor="transparent"
            cooldownTime={hierarchical ? 0 : 1500}
            d3AlphaDecay={hierarchical ? 0 : 0.015}
            d3VelocityDecay={hierarchical ? 0 : 0.3}
            warmupTicks={hierarchical ? 0 : 100}
          />
        </div>

        {selectedNode && (
          <div className="w-80 bg-card border-l border-border p-6 overflow-y-auto">
            <div className="flex justify-between items-start mb-4">
              <h2 className="text-lg font-semibold text-foreground">
                {selectedNode.type === 'link' ? 'Link Details' : selectedNode.label}
              </h2>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </div>

            <div className="space-y-4">
              {selectedNode.type === 'link' ? (
                <>
                  <div>
                    <p className="text-sm text-muted-foreground">Source</p>
                    <p className="font-medium text-foreground">{selectedNode.source}</p>
                    {selectedNode.source_port && (
                      <p className="text-sm text-muted-foreground">Port: {selectedNode.source_port}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Target</p>
                    <p className="font-medium text-foreground">{selectedNode.target}</p>
                    {selectedNode.target_port && (
                      <p className="text-sm text-muted-foreground">Port: {selectedNode.target_port}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Status</p>
                    <div className={`inline-block px-2 py-1 rounded-sm text-xs font-medium ${
                        selectedNode.status === 'active'
                          ? 'bg-badge-success-bg text-badge-success-fg'
                          : 'bg-badge-neutral-bg text-badge-neutral-fg'
                      }`}>
                        {selectedNode.status}
                      </div>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <p className="text-sm text-muted-foreground">Node ID</p>
                    <p className="font-mono text-sm text-foreground">{selectedNode.id}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Label</p>
                    <p className="font-medium text-foreground">{selectedNode.label}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Type</p>
                    <p className="text-foreground capitalize">{selectedNode.node_type}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Status</p>
                      <span
                        className={`inline-block px-2 py-1 rounded-sm text-xs font-medium ${
                          selectedNode.status === 'online'
                            ? 'bg-badge-success-bg text-badge-success-fg'
                            : selectedNode.status === 'offline'
                            ? 'bg-badge-destructive-bg text-badge-destructive-fg'
                            : 'bg-badge-neutral-bg text-badge-neutral-fg'
                        }`}
                      >
                        {selectedNode.status}
                      </span>
                  </div>
                  {selectedNode.device_id && (
                    <div>
                      <p className="text-sm text-muted-foreground">Device ID</p>
                      <p className="font-mono text-sm text-foreground">{selectedNode.device_id}</p>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Topology;