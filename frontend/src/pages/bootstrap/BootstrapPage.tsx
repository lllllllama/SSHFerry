import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { useI18n } from '../../i18n';
import { useAuthStore } from '../../store/auth';

export function BootstrapPage() {
  const navigate = useNavigate();
  const status = useAuthStore((state) => state.status);
  const error = useAuthStore((state) => state.initError);
  const { t } = useI18n();

  useEffect(() => {
    if (status === 'ready') {
      navigate('/workspace', { replace: true });
    }
  }, [navigate, status]);

  return (
    <main className="bootstrap-page">
      <section className="bootstrap-panel">
        <div className="eyebrow">{t('brand.frontend')}</div>
        <h1>{t('bootstrap.title')}</h1>
        {status === 'error' ? (
          <>
            <p className="bootstrap-error">{error || t('bootstrap.error')}</p>
            <button type="button" className="primary-button" onClick={() => window.location.reload()}>
              {t('bootstrap.retry')}
            </button>
          </>
        ) : (
          <>
            <p>{t('bootstrap.description')}</p>
            <div className="bootstrap-progress">
              <span className="progress-ping" />
              <span>{status === 'ready' ? t('bootstrap.complete') : t('bootstrap.connecting')}</span>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
