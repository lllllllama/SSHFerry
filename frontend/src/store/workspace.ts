import { create } from 'zustand';

import type { SessionResponse } from '../api/types';

export type CenterPanelMode = 'local' | 'remote';

export interface RemotePaneState {
  sessionId: string;
  siteName: string;
  currentPath: string;
  pathDraft: string;
  stale: boolean;
}

interface WorkspaceState {
  selectedSiteName: string | null;
  localCurrentPath: string;
  localPathDraft: string;
  localSelection: string[];
  panes: RemotePaneState[];
  activePaneId: string | null;
  centerPanelMode: CenterPanelMode;
  centerSessionId: string | null;
  remoteSelections: Record<string, string[]>;
  setSelectedSiteName: (siteName: string | null) => void;
  setLocalPath: (path: string) => void;
  setLocalPathDraft: (path: string) => void;
  setLocalSelection: (paths: string[]) => void;
  toggleLocalSelection: (path: string, multi: boolean) => void;
  syncSessions: (sessions: SessionResponse[]) => void;
  upsertPane: (session: SessionResponse) => void;
  closePane: (sessionId: string) => void;
  setActivePane: (sessionId: string | null) => void;
  setCenterPanelMode: (mode: CenterPanelMode) => void;
  setCenterSessionId: (sessionId: string | null) => void;
  setPanePath: (sessionId: string, path: string) => void;
  setPanePathDraft: (sessionId: string, path: string) => void;
  setPaneStale: (sessionId: string, stale: boolean) => void;
  setRemoteSelection: (sessionId: string, paths: string[]) => void;
  toggleRemoteSelection: (sessionId: string, path: string, multi: boolean) => void;
}

function upsertSessionPane(panes: RemotePaneState[], session: SessionResponse): RemotePaneState[] {
  const existing = panes.find((pane) => pane.sessionId === session.session_id);
  if (!existing) {
    return [
      ...panes,
      {
        sessionId: session.session_id,
        siteName: session.site_name,
        currentPath: session.remote_root,
        pathDraft: session.remote_root,
        stale: false,
      },
    ];
  }

  return panes.map((pane) =>
    pane.sessionId === session.session_id
      ? {
          ...pane,
          siteName: session.site_name,
          currentPath: pane.currentPath || session.remote_root,
          pathDraft: pane.pathDraft || pane.currentPath || session.remote_root,
        }
      : pane,
  );
}

function resolveCenterSessionId(
  panes: RemotePaneState[],
  currentCenterSessionId: string | null,
  fallbackSessionId: string | null,
): string | null {
  if (currentCenterSessionId && panes.some((pane) => pane.sessionId === currentCenterSessionId)) {
    return currentCenterSessionId;
  }
  if (fallbackSessionId && panes.some((pane) => pane.sessionId === fallbackSessionId)) {
    return fallbackSessionId;
  }
  return panes.at(-1)?.sessionId ?? null;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedSiteName: null,
  localCurrentPath: '',
  localPathDraft: '',
  localSelection: [],
  panes: [],
  activePaneId: null,
  centerPanelMode: 'local',
  centerSessionId: null,
  remoteSelections: {},
  setSelectedSiteName: (siteName) => set({ selectedSiteName: siteName }),
  setLocalPath: (path) => set({ localCurrentPath: path, localPathDraft: path, localSelection: [] }),
  setLocalPathDraft: (path) => set({ localPathDraft: path }),
  setLocalSelection: (paths) => set({ localSelection: paths }),
  toggleLocalSelection: (path, multi) =>
    set((state) => {
      if (!multi) {
        return { localSelection: [path] };
      }
      const selected = state.localSelection.includes(path)
        ? state.localSelection.filter((value) => value !== path)
        : [...state.localSelection, path];
      return { localSelection: selected };
    }),
  syncSessions: (sessions) =>
    set((state) => {
      const nextPanes = sessions.reduce<RemotePaneState[]>(
        (accumulator, session) => upsertSessionPane(accumulator, session),
        [],
      );
      const nextSelections = Object.fromEntries(
        Object.entries(state.remoteSelections).filter(([sessionId]) =>
          sessions.some((session) => session.session_id === sessionId),
        ),
      );
      const fallbackActive =
        state.activePaneId && nextPanes.some((pane) => pane.sessionId === state.activePaneId)
          ? state.activePaneId
          : nextPanes.at(-1)?.sessionId ?? null;
      const nextCenterSessionId = resolveCenterSessionId(nextPanes, state.centerSessionId, fallbackActive);
      return {
        panes: nextPanes,
        activePaneId: fallbackActive,
        centerSessionId: nextCenterSessionId,
        centerPanelMode: state.centerPanelMode === 'remote' && !nextCenterSessionId ? 'local' : state.centerPanelMode,
        remoteSelections: nextSelections,
      };
    }),
  upsertPane: (session) =>
    set((state) => {
      const panes = upsertSessionPane(state.panes, session);
      const centerSessionId = state.centerSessionId ?? session.session_id;
      return {
        panes,
        activePaneId: session.session_id,
        centerSessionId,
      };
    }),
  closePane: (sessionId) =>
    set((state) => {
      const panes = state.panes.filter((pane) => pane.sessionId !== sessionId);
      const remoteSelections = { ...state.remoteSelections };
      delete remoteSelections[sessionId];
      const nextActivePaneId =
        state.activePaneId === sessionId ? panes.at(-1)?.sessionId ?? null : state.activePaneId;
      const nextCenterSessionId =
        state.centerSessionId === sessionId ? resolveCenterSessionId(panes, null, nextActivePaneId) : state.centerSessionId;
      return {
        panes,
        activePaneId: nextActivePaneId,
        centerSessionId: nextCenterSessionId,
        centerPanelMode: state.centerPanelMode === 'remote' && !nextCenterSessionId ? 'local' : state.centerPanelMode,
        remoteSelections,
      };
    }),
  setActivePane: (sessionId) => set({ activePaneId: sessionId }),
  setCenterPanelMode: (mode) =>
    set((state) => {
      const centerSessionId =
        mode === 'remote'
          ? resolveCenterSessionId(state.panes, state.centerSessionId, state.activePaneId)
          : state.centerSessionId;
      return {
        centerPanelMode: mode,
        centerSessionId,
        activePaneId: mode === 'remote' ? centerSessionId ?? state.activePaneId : state.activePaneId,
      };
    }),
  setCenterSessionId: (sessionId) =>
    set((state) => ({
      centerSessionId: sessionId,
      activePaneId: sessionId ?? state.activePaneId,
    })),
  setPanePath: (sessionId, path) =>
    set((state) => ({
      panes: state.panes.map((pane) =>
        pane.sessionId === sessionId
          ? {
              ...pane,
              currentPath: path,
              pathDraft: path,
              stale: false,
            }
          : pane,
      ),
      remoteSelections: {
        ...state.remoteSelections,
        [sessionId]: [],
      },
    })),
  setPanePathDraft: (sessionId, path) =>
    set((state) => ({
      panes: state.panes.map((pane) =>
        pane.sessionId === sessionId
          ? {
              ...pane,
              pathDraft: path,
            }
          : pane,
      ),
    })),
  setPaneStale: (sessionId, stale) =>
    set((state) => ({
      panes: state.panes.map((pane) =>
        pane.sessionId === sessionId
          ? {
              ...pane,
              stale,
            }
          : pane,
      ),
    })),
  setRemoteSelection: (sessionId, paths) =>
    set((state) => ({
      remoteSelections: {
        ...state.remoteSelections,
        [sessionId]: paths,
      },
    })),
  toggleRemoteSelection: (sessionId, path, multi) =>
    set((state) => {
      const current = state.remoteSelections[sessionId] ?? [];
      const next = !multi
        ? [path]
        : current.includes(path)
          ? current.filter((value) => value !== path)
          : [...current, path];
      return {
        remoteSelections: {
          ...state.remoteSelections,
          [sessionId]: next,
        },
        activePaneId: sessionId,
      };
    }),
}));

export function getActivePane() {
  const { activePaneId, panes } = useWorkspaceStore.getState();
  return panes.find((pane) => pane.sessionId === activePaneId) ?? null;
}

export function getRemoteSelection(sessionId: string): string[] {
  return useWorkspaceStore.getState().remoteSelections[sessionId] ?? [];
}

export function hasOpenPaneForSite(siteName: string): boolean {
  return useWorkspaceStore.getState().panes.some((pane) => pane.siteName === siteName);
}
