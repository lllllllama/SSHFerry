import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { listTasks } from '../api/tasks';
import type { TaskItem } from '../api/types';
import { getTaskSocketUrl, parseTaskSocketMessage } from '../api/ws';
import { translate } from '../i18n';
import { useAuthStore } from '../store/auth';
import { useTasksStore } from '../store/tasks';
import { useUiStore } from '../store/ui';

const POLL_INTERVAL_MS = 4000;
const RECONNECT_DELAY_MS = 2200;
const MAX_RECONNECT_BEFORE_POLLING = 3;

export function useTaskSocket() {
  const queryClient = useQueryClient();
  const authReady = useAuthStore((state) => state.status === 'authenticated');
  const setRemoteSnapshot = useTasksStore((state) => state.setRemoteSnapshot);
  const setSocketStatus = useTasksStore((state) => state.setSocketStatus);
  const setSocketError = useTasksStore((state) => state.setSocketError);
  const pushToast = useUiStore((state) => state.pushToast);

  useEffect(() => {
    if (!authReady) {
      return undefined;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pollTimer: number | null = null;
    let reconnectAttempts = 0;
    let disposed = false;
    let unfinishedTaskIds = new Set<string>();

    const applySnapshot = (items: TaskItem[], total: number) => {
      const hasNewlyFinishedTask = items.some(
        (task) => task.is_finished && unfinishedTaskIds.has(task.task_id),
      );
      unfinishedTaskIds = new Set(items.filter((task) => !task.is_finished).map((task) => task.task_id));
      setRemoteSnapshot(items, total);
      if (hasNewlyFinishedTask) {
        // Transfers change directory contents; refresh remote and workspace listings.
        void queryClient.invalidateQueries({ queryKey: ['remote-list'] });
        void queryClient.invalidateQueries({ queryKey: ['workspace-list'] });
        void queryClient.invalidateQueries({ queryKey: ['workspace-stat'] });
        void queryClient.invalidateQueries({ queryKey: ['local-files-list'] });
      }
    };

    const pollTasks = async () => {
      try {
        const snapshot = await listTasks();
        applySnapshot(snapshot.items, snapshot.total);
      } catch (error) {
        setSocketError(error instanceof Error ? error.message : translate('socket.pollFailed'));
      }
    };

    const stopPolling = () => {
      if (pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    const startPolling = () => {
      setSocketStatus('polling');
      void pollTasks();
      if (!pollTimer) {
        pollTimer = window.setInterval(() => {
          void pollTasks();
        }, POLL_INTERVAL_MS);
      }
    };

    const connect = () => {
      if (disposed) {
        return;
      }

      setSocketStatus(reconnectAttempts > 0 ? 'reconnecting' : 'connecting');
      socket = new WebSocket(getTaskSocketUrl());

      socket.onopen = () => {
        reconnectAttempts = 0;
        stopPolling();
        setSocketStatus('connected');
        setSocketError(null);
      };

      socket.onmessage = (event) => {
        const payload = parseTaskSocketMessage(event.data);
        if (!payload) {
          return;
        }

        if (payload.type === 'task_snapshot') {
          applySnapshot(payload.items, payload.total);
          return;
        }

        setSocketError(payload.detail);
        pushToast({
          tone: 'warning',
          title: translate('socket.channelErrorTitle'),
          message: payload.detail,
        });
      };

      socket.onclose = () => {
        if (disposed) {
          return;
        }
        reconnectAttempts += 1;
        if (reconnectAttempts >= MAX_RECONNECT_BEFORE_POLLING) {
          startPolling();
        }
        reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
      };

      socket.onerror = () => {
        setSocketError(translate('socket.websocketError'));
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      stopPolling();
      if (socket && socket.readyState < WebSocket.CLOSING) {
        socket.close();
      }
      setSocketStatus('idle');
    };
  }, [authReady, pushToast, queryClient, setRemoteSnapshot, setSocketError, setSocketStatus]);
}