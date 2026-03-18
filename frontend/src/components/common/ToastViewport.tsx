import { useEffect } from 'react';

import { useUiStore } from '../../store/ui';

const TOAST_TTL_MS = 4200;

export function ToastViewport() {
  const toasts = useUiStore((state) => state.toasts);
  const dismissToast = useUiStore((state) => state.dismissToast);

  useEffect(() => {
    const timers = toasts.map((toast) =>
      window.setTimeout(() => {
        dismissToast(toast.id);
      }, TOAST_TTL_MS),
    );

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [dismissToast, toasts]);

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
            收起
          </button>
        </article>
      ))}
    </aside>
  );
}
