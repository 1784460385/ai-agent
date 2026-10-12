import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { ApiError } from '../api/http';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui/Button';

export function LoginPage() {
  const { user, login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/chat" replace />;

  const submit = async () => {
    setError('');
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : '用户名或密码错误';
      setError(message || '用户名或密码错误');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="hidden flex-col justify-between bg-slate-900 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <span className="h-12 w-12 rounded-2xl bg-gradient-to-br from-orange-400 to-orange-600" />
          <div>
            <strong className="text-2xl tracking-wide">星澜</strong>
            <p className="text-sm text-slate-400">知识库问答平台</p>
          </div>
        </div>
        <p className="max-w-md text-lg leading-8 text-slate-300">登录后按文件夹检索资料，再生成带来源的回答。</p>
      </section>
      <section className="flex items-center justify-center bg-slate-50 p-6">
        <form
          className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <span className="h-10 w-10 rounded-xl bg-gradient-to-br from-orange-400 to-orange-600" />
            <strong className="text-xl">星澜</strong>
          </div>
          <h1 className="text-2xl font-semibold text-slate-900">登录</h1>
          <p className="mt-2 text-sm text-slate-500">使用管理员分配的账号进入平台。</p>
          <label className="mt-6 mb-1 block text-sm text-slate-600" htmlFor="username">
            用户名
          </label>
          <input
            id="username"
            value={username}
            autoComplete="username"
            onChange={(event) => setUsername(event.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-500"
          />
          <label className="mt-4 mb-1 block text-sm text-slate-600" htmlFor="password">
            密码
          </label>
          <input
            id="password"
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-500"
          />
          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
          <Button className="mt-6 w-full" type="submit" disabled={busy}>
            {busy ? '登录中…' : '登录'}
          </Button>
          <p className="mt-4 text-center text-xs leading-5 text-slate-400">账号由管理员统一分配，如需开通请联系管理员。</p>
        </form>
      </section>
    </div>
  );
}
