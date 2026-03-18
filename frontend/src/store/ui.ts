import { create } from 'zustand';

import type { ProtocolOverride, SiteResponse } from '../api/types';

export interface ToastItem {
  id: string;
  tone: 'info' | 'success' | 'warning' | 'danger';
  title: string;
  message?: string;
}

interface SiteEditorState {
  open: boolean;
  site: SiteResponse | null;
}

interface ConfirmState {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  destructive: boolean;
  onConfirm: (() => void | Promise<void>) | null;
}

interface UiState {
  protocolOverride: ProtocolOverride;
  taskCenterExpanded: boolean;
  siteEditor: SiteEditorState;
  confirm: ConfirmState;
  toasts: ToastItem[];
  setProtocolOverride: (value: ProtocolOverride) => void;
  setTaskCenterExpanded: (expanded: boolean) => void;
  openSiteEditor: (site?: SiteResponse | null) => void;
  closeSiteEditor: () => void;
  openConfirm: (options: Omit<ConfirmState, 'open'>) => void;
  closeConfirm: () => void;
  pushToast: (toast: Omit<ToastItem, 'id'>) => void;
  dismissToast: (id: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  protocolOverride: 'auto',
  taskCenterExpanded: true,
  siteEditor: { open: false, site: null },
  confirm: {
    open: false,
    title: '',
    description: '',
    confirmLabel: '',
    destructive: false,
    onConfirm: null,
  },
  toasts: [],
  setProtocolOverride: (value) => set({ protocolOverride: value }),
  setTaskCenterExpanded: (expanded) => set({ taskCenterExpanded: expanded }),
  openSiteEditor: (site = null) => set({ siteEditor: { open: true, site } }),
  closeSiteEditor: () => set({ siteEditor: { open: false, site: null } }),
  openConfirm: (options) =>
    set({
      confirm: {
        ...options,
        open: true,
      },
    }),
  closeConfirm: () =>
    set((state) => ({
      confirm: {
        ...state.confirm,
        open: false,
        onConfirm: null,
      },
    })),
  pushToast: (toast) =>
    set((state) => ({
      toasts: [
        ...state.toasts,
        {
          ...toast,
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        },
      ],
    })),
  dismissToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    })),
}));
