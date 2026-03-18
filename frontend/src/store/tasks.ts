import { create } from 'zustand';

import type { TaskItem } from '../api/types';

export type TaskSocketStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'polling' | 'error';

interface TasksState {
  items: TaskItem[];
  total: number;
  socketStatus: TaskSocketStatus;
  socketError: string | null;
  setSnapshot: (items: TaskItem[], total: number) => void;
  setSocketStatus: (status: TaskSocketStatus) => void;
  setSocketError: (message: string | null) => void;
}

export const useTasksStore = create<TasksState>((set) => ({
  items: [],
  total: 0,
  socketStatus: 'idle',
  socketError: null,
  setSnapshot: (items, total) => set({ items, total }),
  setSocketStatus: (status) => set({ socketStatus: status }),
  setSocketError: (message) => set({ socketError: message }),
}));
