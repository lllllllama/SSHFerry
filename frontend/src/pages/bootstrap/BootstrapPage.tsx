import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuthStore } from '../../store/auth';

export function BootstrapPage() {
  const navigate = useNavigate();
  const status = useAuthStore((state) => state.status);
  const error = useAuthStore((state) => state.initError);

  useEffect(() => {
    if (status === 'ready') {
      navigate('/workspace', { replace: true });
    }
  }, [navigate, status]);

  return (
    <main className="bootstrap-page">
      <section className="bootstrap-panel">
        <div className="eyebrow">SSHFerry Frontend</div>
        <h1>初始化本地工作区</h1>
        {status === 'error' ? (
          <>
            <p className="bootstrap-error">{error || '初始化失败'}</p>
            <button type="button" className="primary-button" onClick={() => window.location.reload()}>
              重试初始化
            </button>
          </>
        ) : (
          <>
            <p>
              正在检查本地 FastAPI 后端、申请本地 token，并准备站点、会话与任务通道。
            </p>
            <div className="bootstrap-progress">
              <span className="progress-ping" />
              <span>{status === 'ready' ? '准备完成' : '连接中...'}</span>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
