import { Skeleton } from '@/components/ui/skeleton';

interface CardSkeletonProps {
  /** Number of skeleton artifacts to render. Default: 6 */
  count?: number;
}

/**
 * CardSkeleton - Loading placeholder for artifact grid
 * 
 * Mimics the structure of CardPreview to provide a smooth loading experience.
 * Uses shadcn/ui Skeleton component with pulsing animation.
 * 
 * @example
 * ```tsx
 * // Show 6 skeleton artifacts while loading
 * {isLoading ? <CardSkeleton count={6} /> : artifacts.map(...)}
 * ```
 * 
 * @param count - Number of skeleton artifacts to render (default: 6)
 */
export function CardSkeleton({ count = 6 }: CardSkeletonProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="relative rounded border border-gray-200 shadow-sm p-4 bg-white"
        >
          {/* Title */}
          <Skeleton className="h-5 w-3/4 mb-3" />
          
          {/* Content lines */}
          <div className="space-y-2 mb-4">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-4/5" />
          </div>
          
          {/* Footer - date and badge */}
          <div className="flex items-center justify-between mt-4 pt-2 border-t border-gray-100">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-5 w-16 rounded-md" />
          </div>
        </div>
      ))}
    </>
  );
}

/**
 * SidebarItemSkeleton - Loading placeholder for sidebar lists
 * 
 * Shows skeleton loaders for workspace, collection, or MCP server lists
 * in the sidebar while data is being fetched.
 * 
 * @example
 * ```tsx
 * // Show 3 skeleton items while loading workspaces
 * {isLoading ? <SidebarItemSkeleton count={3} /> : workspaces.map(...)}
 * ```
 * 
 * @param count - Number of skeleton items to render (default: 3)
 */
export function SidebarItemSkeleton({ count = 3 }: CardSkeletonProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-2 px-8 py-2 cursor-pointer"
        >
          <Skeleton className="h-4 w-4 rounded" />
          <Skeleton className="h-4 flex-1" />
        </div>
      ))}
    </>
  );
}
