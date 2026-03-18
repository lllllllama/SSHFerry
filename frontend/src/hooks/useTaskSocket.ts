import { useEffect } from 'react';

import { listTasks } from '../api/tasks';
import { getTaskSocketUrl, parseTaskSocketMessage } from '../api/ws';
import { translate } from '../i18n';
import { useAuthStore } from '../store/auth';
import { useTasksStore } from '../store/tasks';
import { useUiStore } from '../store/ui';

const POLL_INTERVAL_MS = 4000;
const RECONNECT_DELAY_MS = 2200;
const MAX_RECONNECT_BEFORE_POLLING = 3;

export function useTaskSocket() {
  const token = useAuthStore((state) => state.token);
  const authReady = useAuthStore((state) => state.status === 'ready');
  const setSnapshot = useTasksStore((state) => state.setSnapshot);
  const setSocketStatus = useTasksStore((state) => state.setSocketStatus);
  const setSocketError = useTasksStore((state) => state.setSocketError);
  const pushToast = useUiStore((state) => state.pushToast);

  useEffect(() => {
    if (!authReady || !token) {
      return undefined;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pollTimer: number | null = null;
    let reconnectAttempts = 0;
    let disposed = false;

    const pollTasks = async () => {
      try {
        const snapshot = await listTasks();
        setSnapshot(snapshot.items, snapshot.total);
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
      socket = new WebSocket(getTaskSocketUrl(token));

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
          setSnapshot(payload.items, payload.total);
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
  }, [authReady, pushToast, setSnapshot, setSocketError, setSocketStatus, token]);
}
