import { useRef, useMemo, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { RefreshCw, ZoomIn, ZoomOut } from 'lucide-react';
import { useTopology } from '../hooks/useTopology';

export function Topology() {
  const { topology, isLoading, refresh, isStreaming, lastUpdate } = useTopology();
  const graphRef = useRef<any>(null);
  const [selectedNode, setSelectedNode] = useState<any>(null);

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
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
          <p className="text-gray-600 dark:text-gray-400 mt-4">Loading topology...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50 dark:bg-gray-900">
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center space-x-3">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Network Topology</h1>
              <div
                className={`flex items-center space-x-1.5 px-2 py-1 rounded-full text-xs font-medium ${
                  isStreaming
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                    : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                }`}
                title={isStreaming ? 'Receiving real-time updates' : 'Stream disconnected - attempting reconnect'}
              >
                <div className={`h-2 w-2 rounded-full ${isStreaming ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
                <span className="hidden sm:inline">{isStreaming ? 'Live' : 'Connecting...'}</span>
              </div>
            </div>
            <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
              {graphData.nodes.length} nodes • {graphData.links.length} links
              {lastUpdate && (
                <span className="ml-2">
                  • Updated {lastUpdate.toLocaleTimeString()}
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => graphRef.current?.zoom(1.5)}
              className="p-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              title="Zoom In"
            >
              <ZoomIn className="h-5 w-5" />
            </button>
            <button
              onClick={() => graphRef.current?.zoom(0.5)}
              className="p-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              title="Zoom Out"
            >
              <ZoomOut className="h-5 w-5" />
            </button>
            <button
              onClick={refresh}
              className="flex items-center space-x-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
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
            nodeColor={(node: any) =>
              node.status === 'online'
                ? '#22c55e'
                : node.status === 'offline'
                ? '#ef4444'
                : '#6b7280'
            }
            nodeRelSize={8}
            linkColor={() => '#3b82f6'}
            linkWidth={2}
            nodeLabel={(node: any) => `${node.label}\nStatus: ${node.status}`}
            linkLabel={(link: any) =>
              `${link.source_port || ''} → ${link.target_port || ''}`
            }
            onNodeClick={handleNodeClick}
            onLinkClick={handleLinkClick}
            backgroundColor="#f9fafb"
            cooldownTime={1000}
            d3AlphaDecay={0.02}
          />
        </div>

        {selectedNode && (
          <div className="w-80 bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 p-6 overflow-y-auto">
            <div className="flex justify-between items-start mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {selectedNode.type === 'link' ? 'Link Details' : selectedNode.label}
              </h2>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
              >
                ×
              </button>
            </div>

            <div className="space-y-4">
              {selectedNode.type === 'link' ? (
                <>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Source</p>
                    <p className="font-medium text-gray-900 dark:text-white">{selectedNode.source}</p>
                    {selectedNode.source_port && (
                      <p className="text-sm text-gray-600 dark:text-gray-400">Port: {selectedNode.source_port}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Target</p>
                    <p className="font-medium text-gray-900 dark:text-white">{selectedNode.target}</p>
                    {selectedNode.target_port && (
                      <p className="text-sm text-gray-600 dark:text-gray-400">Port: {selectedNode.target_port}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Status</p>
                    <span
                      className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${
                        selectedNode.status === 'active'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {selectedNode.status}
                    </span>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Node ID</p>
                    <p className="font-mono text-sm text-gray-900 dark:text-white">{selectedNode.id}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Label</p>
                    <p className="font-medium text-gray-900 dark:text-white">{selectedNode.label}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Type</p>
                    <p className="text-gray-900 dark:text-white capitalize">{selectedNode.node_type}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Status</p>
                    <span
                      className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${
                        selectedNode.status === 'online'
                          ? 'bg-green-100 text-green-700'
                          : selectedNode.status === 'offline'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {selectedNode.status}
                    </span>
                  </div>
                  {selectedNode.device_id && (
                    <div>
                      <p className="text-sm text-gray-500 dark:text-gray-400">Device ID</p>
                      <p className="font-mono text-sm text-gray-900 dark:text-white">{selectedNode.device_id}</p>
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
