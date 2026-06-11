import { useRef, useMemo, useState, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { RefreshCw, ZoomIn, ZoomOut, LayoutTemplate, GitBranch, Maximize, RotateCcw } from 'lucide-react';
import { useTopology } from '../hooks/useTopology';
import { useDeviceEvents, useNetworks } from '../hooks';
import { FilterSelect } from '../components/ui/FilterSelect';

function toColor(val: string): string {
  return /^\d/.test(val) ? `hsl(${val})` : val;
}

const COLORS: Record<string, string> = {};

function readCanvasColors() {
  const cs = getComputedStyle(window.document.documentElement);
  const read = (name: string) => toColor(cs.getPropertyValue(name).trim());
  COLORS['haloBg']      = read('--canvas-halo-bg');
  COLORS['haloFg']      = read('--canvas-halo-fg');
  COLORS['nodeStroke']  = read('--canvas-node-stroke');
  COLORS['canvasShadow']= read('--canvas-shadow');
  COLORS['router']      = read('--canvas-router');
  COLORS['switch']      = read('--canvas-switch');
  COLORS['firewall']    = read('--canvas-firewall');
  COLORS['default']     = read('--canvas-default');
  COLORS['online']      = read('--canvas-online');
  COLORS['offline']     = read('--canvas-offline');
  COLORS['link']        = read('--canvas-link-color');
}
readCanvasColors();

const observer = new MutationObserver((mutations) => {
  for (const m of mutations) {
    if (m.type === 'attributes' && m.attributeName === 'class') {
      readCanvasColors();
      return;
    }
  }
});
observer.observe(window.document.documentElement, { attributes: true, attributeFilter: ['class'] });

const TYPE_COLORS: Record<string, string> = {
  router: 'var(--canvas-router)',
  switch: 'var(--canvas-switch)',
  firewall: 'var(--canvas-firewall)',
  access_point: 'var(--canvas-router)',
  server: 'var(--canvas-default)',
  host: 'var(--canvas-default)',
  end_device: 'var(--canvas-default)',
};

function drawRouter(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, color: string, globalScale: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = COLORS['nodeStroke'];
  ctx.lineWidth = Math.max(1.2, 1.8 / globalScale);
  for (let i = 0; i < 4; i++) {
    const angle = (i / 4) * Math.PI * 2 - Math.PI / 4;
    ctx.beginPath();
    ctx.moveTo(Math.cos(angle) * r * 0.5, Math.sin(angle) * r * 0.5);
    ctx.lineTo(Math.cos(angle) * (r + Math.max(3, 4 / globalScale)), Math.sin(angle) * (r + Math.max(3, 4 / globalScale)));
    ctx.stroke();
  }
  ctx.restore();
}

function drawSwitch(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, color: string, globalScale: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = color;
  ctx.fillRect(-s, -s * 0.7, s * 2, s * 1.4);
  ctx.strokeStyle = COLORS['nodeStroke'];
  ctx.lineWidth = Math.max(1, 1.5 / globalScale);
  ctx.strokeRect(-s, -s * 0.7, s * 2, s * 1.4);
  const portCount = 4;
  const gap = (s * 1.8) / (portCount + 1);
  const portDot = Math.max(1.5, 2.5 / globalScale);
  for (let i = 0; i < portCount; i++) {
    const px = -s * 0.8 + gap * (i + 1);
    ctx.beginPath();
    ctx.arc(px, 0, portDot, 0, 2 * Math.PI);
    ctx.fillStyle = COLORS['nodeStroke'];
    ctx.fill();
  }
  ctx.restore();
}

function drawFirewall(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, color: string, globalScale: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.beginPath();
  ctx.moveTo(0, -s);
  ctx.lineTo(s, 0);
  ctx.lineTo(0, s);
  ctx.lineTo(-s, 0);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = COLORS['nodeStroke'];
  ctx.lineWidth = Math.max(1, 1.5 / globalScale);
  ctx.stroke();
  ctx.restore();
}

function drawServer(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, color: string, globalScale: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = color;
  ctx.fillRect(-s * 0.5, -s, s, s * 2);
  ctx.strokeStyle = COLORS['nodeStroke'];
  ctx.lineWidth = Math.max(1, 1.5 / globalScale);
  ctx.strokeRect(-s * 0.5, -s, s, s * 2);
  const slotDot = Math.max(1, 1.5 / globalScale);
  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.arc(0, -s * 0.6 + i * s * 0.6, slotDot, 0, 2 * Math.PI);
    ctx.fillStyle = COLORS['nodeStroke'];
    ctx.fill();
  }
  ctx.restore();
}

function drawHost(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, color: string, globalScale: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(0, -s);
  ctx.lineTo(s * 0.8, -s * 0.3);
  ctx.lineTo(s * 0.8, s * 0.3);
  ctx.lineTo(0, s);
  ctx.lineTo(-s * 0.8, s * 0.3);
  ctx.lineTo(-s * 0.8, -s * 0.3);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = COLORS['nodeStroke'];
  ctx.lineWidth = Math.max(1, 1.5 / globalScale);
  ctx.stroke();
  ctx.restore();
}

function drawAccessPoint(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, color: string, globalScale: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(0, 0, s, 0, 2 * Math.PI);
  ctx.fill();
  ctx.strokeStyle = COLORS['nodeStroke'];
  ctx.lineWidth = Math.max(1, 1.5 / globalScale);
  ctx.stroke();
  const arcLen = Math.max(1, 1.5 / globalScale);
  ctx.beginPath();
  ctx.arc(0, 0, s * 2, Math.PI * 0.25, Math.PI * 0.75);
  ctx.lineWidth = arcLen;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(0, 0, s * 3, Math.PI * 0.3, Math.PI * 0.7);
  ctx.lineWidth = arcLen;
  ctx.stroke();
  ctx.restore();
}

function drawNode(node: any, ctx: CanvasRenderingContext2D, globalScale: number) {
  const nameLabel = node.label || node.id;
  const ipLabel = node.id !== nameLabel ? node.id : '';
  const fontSize = Math.max(9, 10 / globalScale);
  const ipFontSize = Math.max(7, 7 / globalScale);
  const nodeRadius = Math.max(6, 10 / globalScale);

  const baseColor = TYPE_COLORS[node.node_type] || COLORS['default'];
  const color = node.status === 'offline' ? COLORS['offline'] : baseColor;

  ctx.save();

  if (node.node_type === 'router') {
    drawRouter(ctx, node.x, node.y, nodeRadius * 2.2, color, globalScale);
  } else if (node.node_type === 'switch') {
    drawSwitch(ctx, node.x, node.y, nodeRadius * 2, color, globalScale);
  } else if (node.node_type === 'firewall') {
    drawFirewall(ctx, node.x, node.y, nodeRadius * 2.4, color, globalScale);
  } else if (node.node_type === 'access_point') {
    drawAccessPoint(ctx, node.x, node.y, nodeRadius * 1.7, color, globalScale);
  } else if (node.node_type === 'server') {
    drawServer(ctx, node.x, node.y, nodeRadius * 2, color, globalScale);
  } else {
    drawHost(ctx, node.x, node.y, nodeRadius * 2, color, globalScale);
  }

  ctx.restore();

  ctx.save();
  ctx.shadowColor = COLORS['canvasShadow'];
  ctx.shadowBlur = 4 / globalScale;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = 2 / globalScale;

  ctx.font = `500 ${fontSize}px IBM Plex Sans, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  const textMetrics = ctx.measureText(nameLabel);
  const textWidth = textMetrics.width;
  const textHeight = fontSize;
  const pad = 3 / globalScale;
  const textY = node.y + nodeRadius * 2.5 + 6 / globalScale;

  ctx.fillStyle = COLORS['haloBg'];
  ctx.beginPath();
  ctx.roundRect(
    node.x - textWidth / 2 - pad,
    textY - pad,
    textWidth + pad * 2,
    textHeight + (ipLabel ? ipFontSize + pad : 0) + pad * 2,
    2 / globalScale,
  );
  ctx.fill();

  ctx.fillStyle = COLORS['haloFg'];
  ctx.fillText(nameLabel, node.x, textY);

  if (ipLabel) {
    ctx.font = `400 ${ipFontSize}px IBM Plex Sans, system-ui, sans-serif`;
    ctx.fillStyle = COLORS['haloFg'] + 'aa';
    ctx.fillText(ipLabel, node.x, textY + textHeight + 1);
  }

  ctx.restore();

  const statusColor = node.status === 'online' ? COLORS['online']
    : node.status === 'offline' ? COLORS['offline']
    : COLORS['default'];
  const dotX = node.x + nodeRadius + 2 / globalScale;
  const dotY = node.y - nodeRadius - 2 / globalScale;
  ctx.beginPath();
  ctx.arc(dotX, dotY, Math.max(2.5, 3 / globalScale), 0, 2 * Math.PI);
  ctx.fillStyle = statusColor;
  ctx.fill();
  ctx.strokeStyle = COLORS['nodeStroke'];
  ctx.lineWidth = Math.max(1, 1.5 / globalScale);
  ctx.stroke();
}

export function Topology() {
  const { topology, isLoading, refresh, isStreaming, lastUpdate } = useTopology();
  useDeviceEvents();
  const { networks } = useNetworks();
  const graphRef = useRef<any>(null);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [hierarchical, setHierarchical] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [networkFilter, setNetworkFilter] = useState<string>('all');

  const handleFit = useCallback(() => {
    graphRef.current?.zoomToFit(400, 20);
  }, []);

  const handleReset = useCallback(() => {
    graphRef.current?.centerAt(0, 0, 400);
    graphRef.current?.zoom(1, 400);
  }, []);

  const graphData = useMemo(() => {
    const filteredNodes = topology.nodes.filter((n) => {
      if (statusFilter !== 'all' && n.status !== statusFilter) return false;
      if (typeFilter !== 'all' && n.node_type !== typeFilter) return false;
      if (networkFilter !== 'all' && n.network_id !== networkFilter) return false;
      return true;
    });
    const nodeIds = new Set(filteredNodes.map(n => n.id));
    const filteredLinks = topology.links.filter(
      (l) => nodeIds.has(l.source_id) && nodeIds.has(l.target_id)
    );

    const parentIdMap = new Map<string, string | undefined>();
    for (const n of filteredNodes) {
      parentIdMap.set(n.id, n.parent_id);
    }

    const orientedLinks = hierarchical
      ? filteredLinks
          .map((l) => {
            const srcParent = parentIdMap.get(l.source_id);
            const tgtParent = parentIdMap.get(l.target_id);
            if (tgtParent === l.source_id) {
              return { source: l.source_id, target: l.target_id, source_port: l.source_port, target_port: l.target_port, status: l.status };
            }
            if (srcParent === l.target_id) {
              return { source: l.target_id, target: l.source_id, source_port: l.target_port, target_port: l.source_port, status: l.status };
            }
            return null;
          })
          .filter((l): l is NonNullable<typeof l> => l !== null)
      : filteredLinks.map((l) => ({
          source: l.source_id,
          target: l.target_id,
          source_port: l.source_port,
          target_port: l.target_port,
          status: l.status,
        }));

    return {
      nodes: filteredNodes.map((n) => ({
        id: n.id,
        label: n.label || n.id,
        status: n.status,
        node_type: n.node_type,
        device_id: n.device_id,
        network_id: n.network_id,
        level: n.level ?? 0,
        parent_id: n.parent_id,
        role: n.role,
      })),
      links: orientedLinks,
    };
  }, [topology.nodes, topology.links, statusFilter, typeFilter, networkFilter, hierarchical]);

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
    return COLORS['link'] || '#a8a8a8';
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
    <div className="h-screen flex flex-col bg-background overflow-hidden">
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
            <p className="text-muted-foreground text-xs mt-1">
              {graphData.nodes.length} nodes • {graphData.links.length} links
              {(statusFilter !== 'all' || typeFilter !== 'all' || networkFilter !== 'all') && (
                <span className="text-foreground font-medium">
                  {' '}(filtered from {topology.nodes.length} nodes)
                </span>
              )}
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
              className={`flex items-center space-x-2 px-3 py-2 rounded-sm text-xs font-medium ${
                hierarchical
                  ? 'bg-ibm-purple text-white'
                  : 'text-muted-foreground hover:bg-surface-hover'
              }`}
              title={hierarchical ? 'Switch to force-directed layout' : 'Switch to hierarchical layout'}
            >
              {hierarchical ? <GitBranch className="h-4 w-4" /> : <LayoutTemplate className="h-4 w-4" />}
              <span className="hidden sm:inline">{hierarchical ? 'Hierarchy' : 'Force'}</span>
            </button>
            <button
              onClick={refresh}
              className="flex items-center space-x-2 px-4 py-2 bg-cisco-teal text-white rounded-sm hover:bg-cisco-teal/70"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-1.5">
          <FilterSelect label="status" value={statusFilter} onChange={setStatusFilter} options={[
            { value: 'online', label: 'online' },
            { value: 'offline', label: 'offline' },
            { value: 'unknown', label: 'unknown' },
          ]} />
          <FilterSelect label="type" value={typeFilter} onChange={setTypeFilter} options={[
            { value: 'router', label: 'router' },
            { value: 'switch', label: 'switch' },
            { value: 'firewall', label: 'firewall' },
            { value: 'access_point', label: 'access point' },
            { value: 'server', label: 'server' },
            { value: 'host', label: 'host' },
            { value: 'end_device', label: 'end device' },
          ]} />
          <FilterSelect
            label="network"
            value={networkFilter}
            onChange={setNetworkFilter}
            options={networks.map((n) => ({ value: n.id, label: n.name }))}
          />
          {(statusFilter !== 'all' || typeFilter !== 'all' || networkFilter !== 'all') && (
            <button
              onClick={() => {
                setStatusFilter('all');
                setTypeFilter('all');
                setNetworkFilter('all');
              }}
              className="text-xs px-2 py-1 text-muted-foreground hover:text-foreground"
            >
              clear
            </button>
          )}
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
            key={hierarchical ? 'dag' : 'force'}
            ref={graphRef}
            graphData={graphData}
            dagMode={hierarchical ? 'td' : undefined}
            dagLevelDistance={hierarchical ? 160 : undefined}
            nodeCanvasObject={drawNode}
            nodeRelSize={10}
            linkColor={linkColorFn}
            linkWidth={2.5}
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
            onEngineStop={() => {
              if (!hierarchical) {
                const fg = graphRef.current;
                if (fg && fg.d3Force && fg.d3ReheatSimulation) {
                  try {
                    fg.d3Force('x', null);
                    fg.d3Force('y', null);
                  } catch {}
                }
              }
            }}
          />
        </div>

        {selectedNode && (
          <div className="w-80 bg-card border-l border-border p-6 overflow-y-auto">
            <div className="flex justify-between items-start mb-4">
              <h2 className="text-xs font-semibold text-foreground">
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
                    <p className="text-xs text-muted-foreground">Source</p>
                    <p className="font-medium text-foreground">{selectedNode.source}</p>
                    {selectedNode.source_port && (
                      <p className="text-xs text-muted-foreground">Port: {selectedNode.source_port}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Target</p>
                    <p className="font-medium text-foreground">{selectedNode.target}</p>
                    {selectedNode.target_port && (
                      <p className="text-xs text-muted-foreground">Port: {selectedNode.target_port}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Status</p>
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
                    <p className="text-xs text-muted-foreground">Node ID</p>
                    <p className="font-mono text-xs text-foreground">{selectedNode.id}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Label</p>
                    <p className="font-medium text-foreground">{selectedNode.label}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Type</p>
                    <p className="text-foreground capitalize">{selectedNode.node_type}</p>
                  </div>
                  {selectedNode.role && (
                    <div>
                      <p className="text-xs text-muted-foreground">Role</p>
                      <p className="text-foreground capitalize">{selectedNode.role}</p>
                    </div>
                  )}
                  <div>
                    <p className="text-xs text-muted-foreground">Status</p>
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
                      <p className="text-xs text-muted-foreground">Device ID</p>
                      <p className="font-mono text-xs text-foreground">{selectedNode.device_id}</p>
                    </div>
                  )}
                  {selectedNode.parent_id && (() => {
                    const parentNode = graphData.nodes.find(n => n.id === selectedNode.parent_id);
                    return (
                      <div>
                        <p className="text-xs text-muted-foreground">Connected to</p>
                        <button
                          onClick={() => {
                            const p = graphData.nodes.find(n => n.id === selectedNode.parent_id);
                            if (p) {
                              setSelectedNode(p);
                              graphRef.current?.centerOn(p, 400);
                            }
                          }}
                          className="font-medium text-foreground hover:text-cisco-teal underline cursor-pointer"
                        >
                          {parentNode?.label || selectedNode.parent_id}
                        </button>
                      </div>
                    );
                  })()}
                  {(() => {
                    const children = graphData.nodes.filter(n => n.parent_id === selectedNode.id);
                    if (children.length === 0) return null;
                    return (
                      <div>
                        <p className="text-xs text-muted-foreground">Children ({children.length})</p>
                        <div className="space-y-1 mt-1">
                          {children.map(child => (
                            <button
                              key={child.id}
                              onClick={() => {
                                setSelectedNode(child);
                                graphRef.current?.centerOn(child, 400);
                              }}
                              className="block text-xs text-foreground hover:text-cisco-teal underline cursor-pointer"
                            >
                              {child.label || child.id}
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
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