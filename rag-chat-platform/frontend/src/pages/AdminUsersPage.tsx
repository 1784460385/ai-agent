import { useEffect, useState } from 'react';
import { createUser, deleteUser, listUsers, updateUser, type AccountUser } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui/Button';

export function AdminUsersPage() {
  const { user: current } = useAuth();
  const [items, setItems] = useState<AccountUser[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [resetId, setResetId] = useState<number | null>(null);
  const [resetPassword, setResetPassword] = useState('');
  const size = 20;
  const pages = Math.max(1, Math.ceil(total / size));

  const load = async (nextPage = page) => {
    const result = await listUsers(nextPage, size);
    setItems(result.items);
    setTotal(result.total);
    setPage(result.page);
  };

  useEffect(() => {
    load(page).catch((err) => setError(err instanceof Error ? err.message : '无法读取用户'));
  }, [page]);

  const submitCreate = async () => {
    setError('');
    try {
      await createUser({ username: username.trim(), password, role });
      setCreating(false);
      setUsername('');
      setPassword('');
      setRole('user');
      await load(1);
      setPage(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败');
    }
  };

  const toggleActive = async (item: AccountUser) => {
    setError('');
    try {
      await updateUser(item.id, { is_active: !item.is_active });
      await load(page);
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失败');
    }
  };

  const submitReset = async () => {
    if (resetId == null) return;
    setError('');
    try {
      await updateUser(resetId, { password: resetPassword });
      setResetId(null);
      setResetPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : '重置失败');
    }
  };

  const remove = async (item: AccountUser) => {
    if (!window.confirm(`删除用户「${item.username}」及其历史记录？`)) return;
    setError('');
    try {
      await deleteUser(item.id);
      await load(page);
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-slate-50">
      <div className="mx-auto max-w-5xl px-4 py-6">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-900">用户管理</h1>
          <Button onClick={() => setCreating(true)}>+ 新建用户</Button>
        </div>
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-100 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">用户名</th>
                <th className="px-4 py-3">角色</th>
                <th className="px-4 py-3">状态</th>
                <th className="px-4 py-3">创建时间</th>
                <th className="px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b border-slate-50">
                  <td className="px-4 py-3">{item.id}</td>
                  <td className="px-4 py-3">{item.username}</td>
                  <td className="px-4 py-3">{item.role === 'admin' ? '管理员' : '普通用户'}</td>
                  <td className="px-4 py-3">{item.is_active ? '启用' : '禁用'}</td>
                  <td className="px-4 py-3">{new Date(item.created_at).toLocaleString('zh-CN', { hour12: false })}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button type="button" className="text-orange-600 hover:underline" onClick={() => void toggleActive(item)}>
                        {item.is_active ? '禁用' : '启用'}
                      </button>
                      <button
                        type="button"
                        className="text-slate-600 hover:underline"
                        onClick={() => {
                          setResetId(item.id);
                          setResetPassword('');
                        }}
                      >
                        重置密码
                      </button>
                      {item.id !== current?.id && (
                        <button type="button" className="text-red-600 hover:underline" onClick={() => void remove(item)}>
                          删除
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {total > size && (
          <div className="mt-4 flex items-center justify-center gap-3 text-sm">
            <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
              上一页
            </Button>
            <span>
              {page} / {pages}
            </span>
            <Button variant="ghost" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>
              下一页
            </Button>
          </div>
        )}
      </div>
      {creating && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4">
          <form
            className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl"
            onSubmit={(event) => {
              event.preventDefault();
              void submitCreate();
            }}
          >
            <h2 className="text-lg font-semibold">新建用户</h2>
            <label className="mt-4 mb-1 block text-xs text-slate-500" htmlFor="new-username">
              用户名
            </label>
            <input id="new-username" value={username} onChange={(event) => setUsername(event.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            <label className="mt-3 mb-1 block text-xs text-slate-500" htmlFor="new-user-password">
              密码
            </label>
            <input id="new-user-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            <label className="mt-3 mb-1 block text-xs text-slate-500" htmlFor="new-role">
              角色
            </label>
            <select id="new-role" value={role} onChange={(event) => setRole(event.target.value as 'user' | 'admin')} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm">
              <option value="user">普通用户</option>
              <option value="admin">管理员</option>
            </select>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" type="button" onClick={() => setCreating(false)}>
                取消
              </Button>
              <Button type="submit">创建</Button>
            </div>
          </form>
        </div>
      )}
      {resetId != null && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4">
          <form
            className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl"
            onSubmit={(event) => {
              event.preventDefault();
              void submitReset();
            }}
          >
            <h2 className="text-lg font-semibold">重置密码</h2>
            <input
              type="password"
              aria-label="新密码"
              value={resetPassword}
              onChange={(event) => setResetPassword(event.target.value)}
              className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" type="button" onClick={() => setResetId(null)}>
                取消
              </Button>
              <Button type="submit">保存</Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
