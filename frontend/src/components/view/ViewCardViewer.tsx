import { useMemo } from 'react';
import type { Artifact } from '@/context/workspace/workspace.types';
import { safeParseArtifactContext, type ArtifactContext } from '@/utils/artifactContext';
import { getContentType, type ViewMode } from '@/registry/content-types';

interface ViewCardViewerProps {
	artifact: Artifact;
	mode?: ViewMode;
	onOpenCollection?: (collectionId: string) => void;
}

/**
 * ViewCardViewer
 *
 * Minimal MVP viewer for "view" artifacts – saved views over other
 * collections/workspaces. For now, supports collection-targeted views and
 * exposes a single "Open collection view" action that delegates to the
 * main layout via onOpenCollection.
 */
export function ViewCardViewer({ artifact, mode = 'floating', onOpenCollection }: ViewCardViewerProps) {
	const contentType = useMemo(() => getContentType(artifact), [artifact]);
	const ctx: ArtifactContext = safeParseArtifactContext(artifact.context);

	// Heuristics for target collection ID
	// Canonical shape (forward-looking):
	// {
	//   "content_type": "application/vnd.agience.view+json",
	//   "target": { "kind": "collection", "id": "..." },
	//   "view": { "mode": "grid" }
	// }
	const target = (ctx?.target ?? ctx?.view?.target) as
		| { kind?: string; id?: string; collection_id?: string }
		| undefined;
	const targetKind = (target?.kind || 'collection').toLowerCase();
	const explicitCollectionId = target?.collection_id || target?.id;
	const fallbackCollectionId = (ctx?.collection_id || ctx?.target_collection_id) as string | undefined;
	const collectionId = targetKind === 'collection' ? (explicitCollectionId || fallbackCollectionId) : undefined;

	const title = ctx.title || ctx.name || contentType.label || 'View';
	const description =
		ctx.description ||
		ctx.summary ||
		'View artifact — saved view over a collection or workspace.';

	return (
		<div className="h-full w-full flex flex-col bg-white">
			<div className="px-4 py-2 border-b flex items-center justify-between">
				<div className="flex flex-col min-w-0">
					<div className="flex items-center gap-2 min-w-0">
						<contentType.icon size={16} />
						<div className="text-sm font-semibold text-gray-900 truncate" title={title}>
							{title}
						</div>
					</div>
					<div className="text-xs text-gray-500 mt-0.5 truncate" title={description}>
						{description}
					</div>
				</div>
				<div className="text-xs text-gray-500 capitalize ml-4 flex-shrink-0">{mode}</div>
			</div>

			<div className="flex-1 flex flex-col items-center justify-center px-6 py-4 text-center text-sm text-gray-600">
				{collectionId ? (
					<>
						<p className="mb-3">
							This view targets collection
							<span className="font-mono text-xs ml-1 break-all">{collectionId}</span>.
						</p>
						<button
							type="button"
							className="inline-flex items-center px-3 py-1.5 rounded border border-teal-500 text-teal-700 text-xs font-medium hover:bg-teal-50 transition-colors"
							onClick={() => onOpenCollection?.(collectionId)}
						>
							Open collection view on desktop
						</button>
					</>
				) : (
					<p className="text-xs text-gray-500">
						This view does not specify a collection target yet. Edit its context to add a{' '}
						<code className="font-mono text-[11px] bg-gray-50 px-1 py-0.5 rounded">
							{"{\"target\": { \"kind\": \"collection\", \"id\": \"...\" }}"}
						</code>
						.
					</p>
				)}
			</div>
		</div>
	);
}

export default ViewCardViewer;
