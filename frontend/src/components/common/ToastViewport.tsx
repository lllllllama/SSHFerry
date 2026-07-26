import { useEffect, useRef } from 'react';

import { useI18n } from '../../i18n';
import { useUiStore } from '../../store/ui';

const TOAST_TTL_MS = 4200;

export function ToastViewport() {
  const toasts = useUiStore((state) => state.toasts);
  const dismissToast = useUiStore((state) => state.dismissToast);
  const timersRef = useRef(new Map<string, number>());
  const { t } = useI18n();

  useEffect(() => {
    const timers = timersRef.current;
    const activeIds = new Set(toasts.map((toast) => toast.id));

    toasts.forEach((toast) => {
      if (timers.has(toast.id)) {
        return;
      }
      timers.set(
        toast.id,
        window.setTimeout(() => {
          timers.delete(toast.id);
          dismissToast(toast.id);
        }, TOAST_TTL_MS),
      );
    });

    timers.forEach((timer, toastId) => {
      if (!activeIds.has(toastId)) {
        window.clearTimeout(timer);
        timers.delete(toastId);
      }
    });
  }, [dismissToast, toasts]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
    };
  }, []);

  if (!toasts.length) {
    return null;
  }

  return (
    <aside className="toast-stack" aria-live="polite">
      {toasts.map((toast) => (
        <article key={toast.id} className={`toast-card toast-${toast.tone}`}>
          <div>
            <strong>{toast.title}</strong>
            {toast.message ? <p>{toast.message}</p> : null}
          </div>
          <button type="button" className="ghost-button" onClick={() => dismissToast(toast.id)}>
            {t('common.dismiss')}
          </button>
        </article>
      ))}
    </aside>
  );
}
