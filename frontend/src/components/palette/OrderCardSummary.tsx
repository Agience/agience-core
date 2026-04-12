import type { Artifact } from '../../context/workspace/workspace.types';
import { getTransformFromArtifact } from '../../context/palette/orderSpec';

function labelForRunType(runType?: string): string {
  switch (runType) {
    case 'palette-run':
      return 'Palette Run';
    case 'llm':
      return 'LLM Prompt';
    case 'mcp-tool':
      return 'MCP Tool';
    case 'flow-run':
      return 'Flow Run';
    case 'host-script':
      return 'Host Script';
    case 'transform-ref':
      return 'Transform Ref';
    case 'order-ref':
      return 'Transform Ref';
    case 'webhook':
      return 'Webhook';
    default:
      return runType || 'Unspecified';
  }
}

export default function TransformCardSummary({
  artifact,
}: {
  artifact: Artifact;
}) {
  const parsed = getTransformFromArtifact(artifact);
  if (!parsed) return null;

  const spec = parsed.spec;
  const panelData = spec.panelData;
  const detailRows = [
    parsed.run?.type ? { label: 'Runner', value: labelForRunType(parsed.run.type) } : null,
    parsed.run?.type === 'mcp-tool' && parsed.run?.tool
      ? { label: 'Tool', value: `${parsed.run.server || 'agience-core'}:${parsed.run.tool}` }
      : null,
    (parsed.run?.type === 'transform-ref' || parsed.run?.type === 'order-ref') && (parsed.run?.transform_id || parsed.run?.transform_id)
      ? { label: 'Transform Ref', value: String(parsed.run.transform_id || parsed.run.transform_id) }
      : null,
    parsed.run?.type === 'webhook' && parsed.run?.url
      ? { label: 'Webhook', value: parsed.run.url }
      : null,
    parsed.run?.type === 'host-script' && parsed.run?.host_policy
      ? { label: 'Host Policy', value: parsed.run.host_policy }
      : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;

  const stats = [
    { label: 'Input', value: `${panelData.input.artifacts.length} artifacts` },
    { label: 'Resources', value: `${panelData.resources.resources.length} refs` },
    { label: 'Tools', value: `${panelData.tools.tools.length}` },
    { label: 'Knowledge', value: `${panelData.knowledge.artifacts.length} artifacts` },
    { label: 'Targets', value: `${panelData.targets.collections.length} collections` },
  ];

  return (
    <div className="rounded-xl border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-blue-50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-white">
          {parsed.kind || 'palette'}
        </span>
        {parsed.subtype && (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-700">
            {parsed.subtype}
          </span>
        )}
        <span className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] font-medium text-blue-700">
          {labelForRunType(parsed.run?.type)}
        </span>
      </div>

      <div className="mt-3 text-sm text-slate-600">
        Saved transform. Open it in the transform dock to edit execution flow and run behavior. Palette remains one implementation of the transform editor.
      </div>

      {detailRows.length > 0 && (
        <div className="mt-4 grid gap-2 md:grid-cols-2">
          {detailRows.map((row) => (
            <div key={`${row.label}:${row.value}`} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{row.label}</div>
              <div className="mt-1 break-all text-sm text-slate-800">{row.value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{stat.label}</div>
            <div className="mt-1 text-sm text-slate-800">{stat.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}