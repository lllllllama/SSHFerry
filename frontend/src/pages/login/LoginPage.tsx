import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { getCaptcha, getHealth, login } from '../../api/auth';
import { getErrorMessage } from '../../api/http';
import { useI18n } from '../../i18n';
import { useAuthStore } from '../../store/auth';

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const status = useAuthStore((state) => state.status);
  const health = useAuthStore((state) => state.health);
  const authNotice = useAuthStore((state) => state.authNotice);
  const setAuthenticated = useAuthStore((state) => state.setAuthenticated);
  const clearAuthNotice = useAuthStore((state) => state.clearAuthNotice);
  const { language, setLanguage, t } = useI18n();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');
  const [captchaId, setCaptchaId] = useState('');
  const [captchaSvg, setCaptchaSvg] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [captchaLoading, setCaptchaLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const redirectTarget = useMemo(() => {
    const state = location.state as { from?: { pathname?: string } } | null;
    return state?.from?.pathname || '/workspace';
  }, [location.state]);

  useEffect(() => {
    if (status === 'authenticated') {
      navigate(redirectTarget, { replace: true });
    }
  }, [navigate, redirectTarget, status]);

  useEffect(() => {
    void refreshCaptcha();
  }, []);

  async function refreshCaptcha() {
    setCaptchaLoading(true);
    try {
      const captcha = await getCaptcha();
      setCaptchaId(captcha.captcha_id);
      setCaptchaSvg(captcha.image_svg);
      setCaptchaCode('');
    } catch (error) {
      setFormError(getErrorMessage(error, t('auth.captchaLoadFailed')));
    } finally {
      setCaptchaLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      const user = await login({ username, password, captcha_id: captchaId, captcha_code: captchaCode });
      const latestHealth = health ?? (await getHealth());
      setAuthenticated({ health: latestHealth, user });
      clearAuthNotice();
      navigate(redirectTarget, { replace: true });
    } catch (error) {
      setFormError(getErrorMessage(error, t('auth.loginFailed')));
      await refreshCaptcha();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="bootstrap-page login-page">
      <section className="bootstrap-panel login-panel">
        <div className="bootstrap-panel-toolbar">
          <div className="eyebrow">{t('brand.frontend')}</div>
          <div className="locale-switch locale-switch-compact" role="group" aria-label={t('topbar.language')}>
            <button type="button" className={`locale-button ${language === 'zh' ? 'is-active' : ''}`} onClick={() => setLanguage('zh')}>
              {t('language.zh')}
            </button>
            <button type="button" className={`locale-button ${language === 'en' ? 'is-active' : ''}`} onClick={() => setLanguage('en')}>
              {t('language.en')}
            </button>
          </div>
        </div>
        <h1>{t('login.title')}</h1>
        <p>{t('login.description')}</p>
        {authNotice ? <div className="login-notice">{authNotice}</div> : null}
        {formError ? <div className="bootstrap-error login-error">{formError}</div> : null}
        <form className="login-form" onSubmit={handleSubmit}>
          <label className="form-field">
            <span>{t('login.username')}</span>
            <input autoComplete="username" name="username" placeholder={t('login.usernamePlaceholder')} value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label className="form-field">
            <span>{t('login.password')}</span>
            <input autoComplete="current-password" name="password" type="password" placeholder={t('login.passwordPlaceholder')} value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <div className="captcha-row">
            <label className="form-field">
              <span>{t('auth.captcha')}</span>
              <input name="captchaCode" placeholder={t('auth.captchaPlaceholder')} value={captchaCode} onChange={(event) => setCaptchaCode(event.target.value.toUpperCase())} />
            </label>
            <div className="captcha-visual-shell">
              <button type="button" className="captcha-visual" onClick={() => void refreshCaptcha()} disabled={captchaLoading} title={t('auth.refreshCaptcha')}>
                {captchaSvg ? <span dangerouslySetInnerHTML={{ __html: captchaSvg }} /> : t('common.loading')}
              </button>
            </div>
          </div>
          <div className="login-actions login-actions-symmetric">
            <button type="submit" className="primary-button login-action-button" disabled={submitting || !captchaId}>
              {submitting ? t('login.submitting') : t('login.submit')}
            </button>
            <Link to="/signup" className="ghost-button login-action-button">
              {t('login.switchAction')}
            </Link>
          </div>
        </form>
      </section>
    </main>
  );
}
