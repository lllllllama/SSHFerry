import { type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { useI18n } from '../../i18n';

interface ModalProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: 'compact' | 'wide';
}

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  width = 'compact',
}: ModalProps) {
  const { t } = useI18n();

  if (!open) {
    return null;
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <section
        className={`modal-shell ${width === 'wide' ? 'modal-shell-wide' : ''}`}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="modal-header">
          <div>
            <h2>{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            {t('common.close')}
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer ? <footer className="modal-footer">{footer}</footer> : null}
      </section>
    </div>,
    document.body,
  );
}
