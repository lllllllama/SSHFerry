import { create } from 'zustand';

import type { SessionResponse } from '../api/types';

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

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedSiteName: null,
  localCurrentPath: '',
  localPathDraft: '',
  localSelection: [],
  panes: [],
  activePaneId: null,
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
      return {
        panes: nextPanes,
        activePaneId: fallbackActive,
        remoteSelections: nextSelections,
      };
    }),
  upsertPane: (session) =>
    set((state) => ({
      panes: upsertSessionPane(state.panes, session),
      activePaneId: session.session_id,
    })),
  closePane: (sessionId) =>
    set((state) => {
      const panes = state.panes.filter((pane) => pane.sessionId !== sessionId);
      const remoteSelections = { ...state.remoteSelections };
      delete remoteSelections[sessionId];
      return {
        panes,
        activePaneId:
          state.activePaneId === sessionId ? panes.at(-1)?.sessionId ?? null : state.activePaneId,
        remoteSelections,
      };
    }),
  setActivePane: (sessionId) => set({ activePaneId: sessionId }),
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
