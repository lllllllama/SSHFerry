import { useI18n } from '../../i18n';

export function LogPlaceholder() {
  const { t } = useI18n();

  return (
    <section className="log-placeholder panel-shell">
      <header className="panel-header">
        <div>
          <h3>{t('log.title')}</h3>
          <p>{t('log.description')}</p>
        </div>
      </header>
      <div className="placeholder-body">
        <strong>{t('log.placeholderTitle')}</strong>
        <p>{t('log.placeholderBody')}</p>
      </div>
    </section>
  );
}
