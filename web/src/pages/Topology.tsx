import { useRef, useMemo, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { RefreshCw, ZoomIn, ZoomOut, Network } from 'lucide-react';
import { useTopology } from '../hooks/useTopology';
import { apiClient } from '../api';

export function Topology() {
  const { topology, isLoading, refresh, isStreaming, lastUpdate } = useTopology();
  const graphRef = useRef<any>(null);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [isSimulating, setIsSimulating] = useState(false);

  const handleSimulate = async () => {
    setIsSimulating(true);
    try {
      await apiClient.post('/topology/simulate');
      await refresh();
    } catch (error) {
      console.error('Failed to simulate topology:', error);
    } finally {
      setIsSimulating(false);
    }
  };

  const graphData = useMemo(() => ({
    nodes: topology.nodes.map((n) => ({
      id: n.id,
      label: n.label || n.id,
      status: n.status,
      node_type: n.node_type,
      device_id: n.device_id,
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
    graphRef.current?.centerOn(node);
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-sm h-12 w-12 border-b-2 border-[#da1e28] mx-auto"></div>
          <p className="text-[#525252] dark:text-[#a8a8a8] mt-4">Loading topology...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[#f4f4f4] dark:bg-[#161616]">
      <div className="bg-white dark:bg-[#262626] border-b border-[#e0e0e0] dark:border-[#393939] px-6 py-4">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center space-x-3">
              <h1 className="text-2xl font-bold text-[#161616] dark:text-white">Network Topology</h1>
              <div
                className={`flex items-center space-x-1.5 px-2 py-1 rounded-sm text-xs font-medium ${
                  isStreaming
                    ? 'bg-[#defbe6] text-[#24a148] dark:bg-[#142811] dark:text-[#42be65]'
                    : 'bg-[#fcf4d6] text-[#b28600] dark:bg-[#3c2e05] dark:text-[#f1c21b]'
                }`}
                title={isStreaming ? 'Receiving real-time updates' : 'Stream disconnected - attempting reconnect'}
              >
                <div className={`h-2 w-2 rounded-sm ${isStreaming ? 'bg-[#24a148] animate-pulse' : 'bg-[#f1c21b]'}`} />
                <span className="hidden sm:inline">{isStreaming ? 'Live' : 'Connecting...'}</span>
              </div>
            </div>
            <p className="text-[#525252] dark:text-[#a8a8a8] text-sm mt-1">
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
              onClick={() => graphRef.current?.zoom(1.5)}
              className="p-2 text-[#525252] dark:text-[#a8a8a8] hover:bg-[#e0e0e0] dark:hover:bg-[#393939] rounded-sm"
              title="Zoom In"
            >
              <ZoomIn className="h-5 w-5" />
            </button>
            <button
              onClick={() => graphRef.current?.zoom(0.5)}
              className="p-2 text-[#525252] dark:text-[#a8a8a8] hover:bg-[#e0e0e0] dark:hover:bg-[#393939] rounded-sm"
              title="Zoom Out"
            >
              <ZoomOut className="h-5 w-5" />
            </button>
            <button
              onClick={handleSimulate}
              disabled={isSimulating}
              className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-sm hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Generate simulated network topology for demo"
            >
              <Network className="h-4 w-4" />
              <span>{isSimulating ? 'Generating...' : 'Simulate Network'}</span>
            </button>
            <button
              onClick={refresh}
              className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 flex">
        <div className="flex-1 relative">
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            nodeColor={(node: any) => {
              // Color by node type first, then adjust by status
              const baseColor = node.node_type === 'router' ? '#da1e28'
                : node.node_type === 'firewall' ? '#f1c21b'
                : node.node_type === 'switch' ? '#0f62fe'
                : '#525252';
              // Dim for offline status
              return node.status === 'offline' ? '#393939' : baseColor;
            }}
            nodeRelSize={10}
            linkColor={() => '#a8a8a8'}
            linkWidth={2.5}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelLen={0.8}
            nodeLabel={(node: any) => `${node.label}\n${node.node_type} • ${node.status}`}
            linkLabel={(link: any) =>
              `${link.source_port || ''} → ${link.target_port || ''}`
            }
            onNodeClick={handleNodeClick}
            onLinkClick={handleLinkClick}
            backgroundColor="transparent"
            cooldownTime={1500}
            d3AlphaDecay={0.015}
            d3VelocityDecay={0.3}
            warmupTicks={100}
          />
        </div>

        {selectedNode && (
          <div className="w-80 bg-white dark:bg-[#262626] border-l border-[#e0e0e0] dark:border-[#393939] p-6 overflow-y-auto">
            <div className="flex justify-between items-start mb-4">
              <h2 className="text-lg font-semibold text-[#161616] dark:text-white">
                {selectedNode.type === 'link' ? 'Link Details' : selectedNode.label}
              </h2>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-[#a8a8a8] dark:text-[#525252] hover:text-[#525252] dark:hover:text-[#c6c6c6]"
              >
                ×
              </button>
            </div>

            <div className="space-y-4">
              {selectedNode.type === 'link' ? (
                <>
                  <div>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Source</p>
                    <p className="font-medium text-[#161616] dark:text-white">{selectedNode.source}</p>
                    {selectedNode.source_port && (
                      <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Port: {selectedNode.source_port}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Target</p>
                    <p className="font-medium text-[#161616] dark:text-white">{selectedNode.target}</p>
                    {selectedNode.target_port && (
                      <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Port: {selectedNode.target_port}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Status</p>
                    <span
                      className={`inline-block px-2 py-1 rounded-sm text-xs font-medium ${
                        selectedNode.status === 'active'
                          ? 'bg-[#defbe6] text-[#24a148]'
                          : 'bg-[#e0e0e0] text-[#161616]'
                      }`}
                    >
                      {selectedNode.status}
                    </span>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Node ID</p>
                    <p className="font-mono text-sm text-[#161616] dark:text-white">{selectedNode.id}</p>
                  </div>
                  <div>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Label</p>
                    <p className="font-medium text-[#161616] dark:text-white">{selectedNode.label}</p>
                  </div>
                  <div>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Type</p>
                    <p className="text-[#161616] dark:text-white capitalize">{selectedNode.node_type}</p>
                  </div>
                  <div>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Status</p>
                    <span
                      className={`inline-block px-2 py-1 rounded-sm text-xs font-medium ${
                        selectedNode.status === 'online'
                          ? 'bg-[#defbe6] text-[#24a148]'
                          : selectedNode.status === 'offline'
                          ? 'bg-[#fff0f1] text-[#da1e28]'
                          : 'bg-[#e0e0e0] text-[#161616]'
                      }`}
                    >
                      {selectedNode.status}
                    </span>
                  </div>
                  {selectedNode.device_id && (
                    <div>
                      <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">Device ID</p>
                      <p className="font-mono text-sm text-[#161616] dark:text-white">{selectedNode.device_id}</p>
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
