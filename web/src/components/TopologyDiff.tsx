import { useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import type { TopologyData, TopologyLink } from '../api';

interface Props {
  before: TopologyData;
  after: TopologyData;
  event: any;
}

function buildGraphData(data: TopologyData) {
  return {
    nodes: data.nodes.map((n) => ({ ...n, id: n.id })),
    links: data.links.map((l) => ({
      ...l,
      source: l.source_id,
      target: l.target_id,
    })),
  };
}

function computeDiff(_before: TopologyData, _after: TopologyData, event: any) {
  const addedNodeIds = new Set<string>();
  const removedNodeIds = new Set<string>();
  const addedLinkIds = new Set<string>();
  const removedLinkIds = new Set<string>();

  const details = event?.details || {};
  if (details.action === 'added') {
    if (details.type === 'node') addedNodeIds.add(event.node_id);
    if (details.type === 'link') addedLinkIds.add(event.link_id);
  }
  if (details.action === 'removed') {
    if (details.type === 'nodes') {
      const ids = details.ids || [];
      ids.forEach((id: string) => removedNodeIds.add(id));
    }
    if (details.type === 'links') {
      const ids = details.ids || [];
      ids.forEach((id: string) => removedLinkIds.add(id));
    }
  }

  return { addedNodeIds, removedNodeIds, addedLinkIds, removedLinkIds };
}

function GraphPanel({
  title,
  data,
  diff,
  variant,
}: {
  title: string;
  data: TopologyData;
  diff: ReturnType<typeof computeDiff>;
  variant: 'before' | 'after';
}) {
  const graphData = useMemo(() => buildGraphData(data), [data]);

  return (
    <div className="flex flex-col h-full">
    <div className="px-3 py-2 border-b border-border bg-card dark:bg-muted">
      <h4 className="text-xs font-medium text-foreground">{title}</h4>
    </div>
      <div className="flex-1 relative">
        {graphData.nodes.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-muted-foreground text-xs">
            No topology data
          </div>
        ) : (
          <ForceGraph2D
            graphData={graphData}
            nodeAutoColorBy="node_type"
            nodeLabel="label"
            linkLabel={(l: any) => `${l.source_port || ''} → ${l.target_port || ''}`}
            width={undefined}
            height={undefined}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const label = node.label || node.id;
              const fontSize = 12 / globalScale;
              ctx.font = `${fontSize}px sans-serif`;

              // Color based on diff
              let fill = '#525252';
              const nodeId = node.id as string;
              if (diff.addedNodeIds.has(nodeId)) fill = variant === 'after' ? '#42be65' : '#525252';
              if (diff.removedNodeIds.has(nodeId)) fill = variant === 'before' ? '#da1e28' : '#525252';

              ctx.fillStyle = fill;
              ctx.beginPath();
              ctx.arc(node.x || 0, node.y || 0, 5 / globalScale, 0, 2 * Math.PI);
              ctx.fill();

              ctx.fillStyle = fill;
              ctx.fillText(label, (node.x || 0) + 6 / globalScale, (node.y || 0) + fontSize / 3);
            }}
            linkColor={(l: any) => {
              const linkId = (l as TopologyLink).id;
              if (diff.addedLinkIds.has(linkId)) return variant === 'after' ? '#42be65' : '#a8a8a8';
              if (diff.removedLinkIds.has(linkId)) return variant === 'before' ? '#da1e28' : '#a8a8a8';
              return '#a8a8a8';
            }}
            linkWidth={1.5}
            backgroundColor="transparent"
            warmupTicks={10}
            cooldownTicks={30}
          />
        )}
      </div>
    </div>
  );
}

export default function TopologyDiff({ before, after, event }: Props) {
  const diff = useMemo(() => computeDiff(before, after, event), [before, after, event]);

  return (
    <div className="flex h-full">
      <div className="flex-1 border-r border-border">
        <GraphPanel title="Before" data={before} diff={diff} variant="before" />
      </div>
      <div className="flex-1">
        <GraphPanel title="After" data={after} diff={diff} variant="after" />
      </div>
    </div>
  );
}
