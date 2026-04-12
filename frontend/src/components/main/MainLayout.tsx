import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ActiveSource } from "../../types/workspace";
import FooterBar from "./MainFooter";
import { WorkspacePanel } from "../workspace/WorkspacePanel";
import HeaderBar from "./MainHeader";
import CommandPalette from "../command-palette/CommandPalette";
import { TwoPanelLayout } from "../layout/TwoPanelLayout";
import { SearchPanel } from "../search/SearchPanel";
import { useWorkspace } from "../../hooks/useWorkspace";
import { useWorkspaces } from "../../hooks/useWorkspaces";
import type { SearchResponse } from "../../api/types/search";
import type { Artifact } from "../../context/workspace/workspace.types";
import FloatingCardWindow from "../windows/FloatingCardWindow";
import { getContentType } from "@/registry/content-types";
import { resolveSearchHitsToArtifacts } from "../../utils/resolveSearchHits";

function MainLayout() {
  const [activeSource, setActiveSource] = useState<ActiveSource>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [searchSortMode, setSearchSortMode] = useState<'relevance' | 'recency'>('relevance');
  const [searchAperture, setSearchAperture] = useState<number>(0.5);
  const [clearSearchTrigger, setClearSearchTrigger] = useState(0);
  // Resolved search result artifacts to display in SearchPanel
  const [resolvedSearchArtifacts, setResolvedSearchArtifacts] = useState<Artifact[]>([]);
  const [isResolvingSearch, setIsResolvingSearch] = useState(false);

  // Floating windows (opened artifacts)
  const [openArtifactWindowIds, setOpenArtifactWindowIds] = useState<string[]>([]);
  const [artifactWindowEditIds, setArtifactWindowEditIds] = useState<string[]>([]);

  // Settings modal state (driven from HeaderBar; SidebarEnhanced no longer triggers these)
  const [settingsInitialSection, setSettingsInitialSection] = useState<
    'profile' | 'general' | 'llm-keys' | 'billing' | 'demo-data' | undefined
  >(undefined);
  const [settingsScopedCollectionId, setSettingsScopedCollectionId] = useState<
    string | undefined
  >(undefined);

  // Get workspace context
  const {
    artifacts,
    displayedArtifacts = [],
    setDisplayedArtifacts,
    unselectAllArtifacts,
    addExistingArtifact,
  } = useWorkspace();
  const { activeWorkspaceId } = useWorkspaces();

  // Panel widths for header coordination
  const [panelWidths, setPanelWidths] = useState<{ left: number; right: number }>({
    left: 340,
    right: 900,
  });
  const [isPanelResizing, setIsPanelResizing] = useState(false);

  const handlePanelWidthsChange = useCallback((widths: { left: number; right: number }) => {
    setPanelWidths((prev) => {
      const tol = 0.5;
      if (Math.abs(prev.left - widths.left) < tol && Math.abs(prev.right - widths.right) < tol) {
        return prev;
      }
      return widths;
    });
  }, []);

  const prevWorkspaceIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!activeWorkspaceId) {
      prevWorkspaceIdRef.current = null;
      return;
    }
    if (prevWorkspaceIdRef.current === activeWorkspaceId) return;
    prevWorkspaceIdRef.current = activeWorkspaceId;

    setActiveSource((prev) => {
      if (!prev || prev.type !== 'workspace' || prev.id !== activeWorkspaceId) {
        return { type: 'workspace', id: activeWorkspaceId };
      }
      return prev;
    });

    setSelectedArtifactId(null);
    unselectAllArtifacts();
    setOpenArtifactWindowIds([]);
  }, [activeWorkspaceId, unselectAllArtifacts]);

  const openOrFocusArtifactWindow = useCallback((artifactId: string, options?: { startInEditMode?: boolean }) => {
    const id = `artifact:${artifactId}`;
    setOpenArtifactWindowIds((prev) => {
      if (prev.includes(id)) {
        return [...prev.filter((x) => x !== id), id];
      }
      return [...prev, id];
    });
    if (options?.startInEditMode) {
      setArtifactWindowEditIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    }
  }, []);

  const closeArtifactWindow = useCallback((windowId: string) => {
    setOpenArtifactWindowIds((prev) => prev.filter((id) => id !== windowId));
    setArtifactWindowEditIds((prev) => prev.filter((id) => id !== windowId));
  }, []);

  const focusArtifactWindow = useCallback((windowId: string) => {
    setOpenArtifactWindowIds((prev) => {
      if (!prev.includes(windowId)) return prev;
      return [...prev.filter((id) => id !== windowId), windowId];
    });
  }, []);

  const handleOpenArtifact = useCallback(
    (artifact: Artifact, options?: { startInEditMode?: boolean }) => {
      const contentType = getContentType(artifact);
      const artifactId = artifact.id ? String(artifact.id) : null;

      if (
        artifactId &&
        typeof setDisplayedArtifacts === 'function' &&
        !artifacts.some((current) => String(current.id) === artifactId)
      ) {
        const nextDisplayedArtifacts = displayedArtifacts.some(
          (current) => String(current.id) === artifactId,
        )
          ? displayedArtifacts.map((current) =>
              String(current.id) === artifactId ? artifact : current,
            )
          : [...displayedArtifacts, artifact];
        setDisplayedArtifacts(nextDisplayedArtifacts);
      }

      if (
        ['tree', 'grid', 'list'].includes(contentType.defaultMode) &&
        !contentType.isContainer &&
        !options?.startInEditMode
      ) {
        return;
      }
      if (artifactId) openOrFocusArtifactWindow(artifactId, options);
    },
    [artifacts, displayedArtifacts, openOrFocusArtifactWindow, setDisplayedArtifacts],
  );

  const openWindows = useMemo(() => {
    return openArtifactWindowIds
      .map((id) => ({
        id,
        artifactId: id.startsWith('artifact:') ? id.slice('artifact:'.length) : id,
      }))
      .filter((w) => Boolean(w.artifactId));
  }, [openArtifactWindowIds]);

  const handleOpenCollectionFromContainer = (collectionId: string) => {
    setActiveSource({ type: 'collection', id: collectionId });
    setSelectedArtifactId(null);
    unselectAllArtifacts();
  };

  // ── Search ──────────────────────────────────────────────────────────────────

  const handleSearchResults = useCallback(async (results: SearchResponse) => {
    if (!results.hits || results.hits.length === 0) {
      setResolvedSearchArtifacts([]);
      return;
    }
    setIsResolvingSearch(true);
    try {
      const artifacts = await resolveSearchHitsToArtifacts(results.hits);
      setResolvedSearchArtifacts(artifacts);
    } catch (err) {
      console.error('[MainLayout] Failed to resolve search hits:', err);
      setResolvedSearchArtifacts([]);
    } finally {
      setIsResolvingSearch(false);
    }
  }, []);

  const handleSearchClear = useCallback(() => {
    setResolvedSearchArtifacts([]);
  }, []);

  const handleAddToWorkspace = useCallback(
    (artifact: Artifact) => {
      addExistingArtifact(artifact);
    },
    [addExistingArtifact],
  );

  useEffect(() => {
    if (!activeWorkspaceId) return;

    const liveArtifactIds = new Set(
      artifacts
        .flatMap((artifact) => [artifact.id, artifact.root_id])
        .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
        .map(String),
    );

    setResolvedSearchArtifacts((prev) => prev.filter((artifact) => {
      if (artifact.collection_id !== activeWorkspaceId) return true;

      const candidates = [artifact.id, artifact.root_id]
        .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
        .map(String);

      if (candidates.length === 0) return false;
      return candidates.some((candidate) => liveArtifactIds.has(candidate));
    }));
  }, [activeWorkspaceId, artifacts]);

  return (
    <div className="flex flex-col h-screen">
      {/* Command Palette (Cmd+K / Ctrl+K) */}
      <CommandPalette
        onWorkspaceSelect={(workspaceId) => {
          setActiveSource({ type: 'workspace', id: workspaceId });
          setResolvedSearchArtifacts([]);
          setClearSearchTrigger((prev) => prev + 1);
          setSelectedArtifactId(null);
          unselectAllArtifacts();
        }}
        onCollectionSelect={(collectionId) => {
          setActiveSource({ type: 'collection', id: collectionId });
          setResolvedSearchArtifacts([]);
          setClearSearchTrigger((prev) => prev + 1);
          setSelectedArtifactId(null);
          unselectAllArtifacts();
        }}
        onMcpServerSelect={(serverId) => {
          setActiveSource({ type: 'mcp-server', id: serverId });
          setResolvedSearchArtifacts([]);
          setClearSearchTrigger((prev) => prev + 1);
          setSelectedArtifactId(null);
          unselectAllArtifacts();
        }}
      />

      {/* Global Header Bar */}
      <HeaderBar
        activeSource={activeSource}
        sidebarWidthPx={panelWidths.left}
        isPanelResizing={isPanelResizing}
        settingsInitialSection={settingsInitialSection}
        settingsScopedCollectionId={settingsScopedCollectionId}
        onSettingsSectionClear={() => {
          setSettingsInitialSection(undefined);
          setSettingsScopedCollectionId(undefined);
        }}
        onArtifactCreated={handleOpenArtifact}
      />

      {/* Two-Panel Layout */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <TwoPanelLayout
          leftPanel={
            <SearchPanel
              artifacts={resolvedSearchArtifacts}
              isLoading={isResolvingSearch}
              onResults={handleSearchResults}
              onClear={handleSearchClear}
              clearTrigger={clearSearchTrigger}
              onAddToWorkspace={handleAddToWorkspace}
              onOpenArtifact={handleOpenArtifact}
              onCollectionSelect={handleOpenCollectionFromContainer}
              sortMode={searchSortMode}
              onSortChange={setSearchSortMode}
              aperture={searchAperture}
              onApertureChange={setSearchAperture}
            />
          }
          rightPanel={
            <WorkspacePanel
              activeSource={activeSource}
              selectedArtifactId={selectedArtifactId}
              searchResultArtifacts={resolvedSearchArtifacts}
              onArtifactSelect={(artifactId) => {
                setSelectedArtifactId(artifactId ?? null);
              }}
              onOpenArtifact={handleOpenArtifact}
              onAssignCollections={(artifactId) => {
                // Collection assignment handled inside Browser.tsx via modal
                void artifactId;
              }}
            />
          }
          onPanelWidthsChange={handlePanelWidthsChange}
          onResizingChange={setIsPanelResizing}
        />

        {/* Floating artifact windows */}
        {openWindows.map((w, idx) => (
          <FloatingCardWindow
            key={w.id}
            artifactId={w.artifactId}
            zIndex={50 + idx}
            windowIndex={idx}
            initialViewState={artifactWindowEditIds.includes(w.id) ? 'edit' : undefined}
            onFocus={() => focusArtifactWindow(w.id)}
            onSnapToGrid={(x, y) => {
              console.log('Snap to grid at', x, y);
              closeArtifactWindow(w.id);
            }}
            onClose={() => closeArtifactWindow(w.id)}
            onOpenCollection={handleOpenCollectionFromContainer}
            onOpenArtifact={handleOpenArtifact}
          />
        ))}
      </div>

      {/* Footer Bar — full width */}
      <FooterBar />
    </div>
  );
}

export default MainLayout;