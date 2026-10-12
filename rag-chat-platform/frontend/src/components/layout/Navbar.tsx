import { Menu, X } from 'lucide-react';
import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { changePassword } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../ui/Button';

const links = [
  { to: '/chat', label: '聊天' },
  { to: '/knowledge', label: '知识库' },
  { to: '/history', label: '历史记录' },
];

export function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordHint, setPasswordHint] = useState('');

  const items = user?.role === 'admin' ? [...links, { to: '/admin/users', label: '用户管理' }] : links;

  const signOut = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const submitPassword = async () => {
    setPasswordError('');
    setPasswordHint('');
    if (newPassword.length < 6) {
      setPasswordError('新密码至少 6 位');
      return;
    }
    try {
      await changePassword(oldPassword, newPassword);
      setPasswordHint('密码已更新');
      setOldPassword('');
      setNewPassword('');
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : '修改失败');
    }
  };

  return (
    <header className="z-30 border-b border-slate-200 bg-white">
      <div className="flex h-16 items-center gap-4 px-4">
        <button type="button" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" aria-label="打开导航" onClick={() => setOpen(true)}>
          <Menu className="h-5 w-5" />
        </button>
        <NavLink to="/chat" className="flex items-center gap-2">
          <span className="h-8 w-8 rounded-lg bg-gradient-to-br from-orange-400 to-orange-600" />
          <strong className="text-lg tracking-wide text-slate-900">星澜</strong>
        </NavLink>
        <nav className="hidden items-center gap-1 lg:flex">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `border-b-2 px-3 py-5 text-sm ${isActive ? 'border-orange-500 text-orange-500' : 'border-transparent text-slate-600 hover:text-slate-900'}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="relative ml-auto">
          <button
            type="button"
            className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm text-slate-700 hover:bg-slate-100"
            aria-label="用户菜单"
            onClick={() => setMenuOpen((value) => !value)}
          >
            <span className="grid h-8 w-8 place-items-center rounded-full bg-orange-100 text-sm font-semibold text-orange-700">
              {user?.username.slice(0, 1).toUpperCase()}
            </span>
            <span className="hidden sm:inline">{user?.username}</span>
          </button>
          {menuOpen && (
            <div className="absolute right-0 mt-2 w-40 rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                onClick={() => {
                  setMenuOpen(false);
                  navigate('/history');
                }}
              >
                历史记录
              </button>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                onClick={() => {
                  setMenuOpen(false);
                  setPasswordOpen(true);
                  setPasswordError('');
                  setPasswordHint('');
                }}
              >
                修改密码
              </button>
              <button type="button" className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50" onClick={signOut}>
                退出登录
              </button>
            </div>
          )}
        </div>
      </div>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button type="button" aria-label="关闭导航" className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(false)} />
          <div className="relative h-full w-64 bg-white p-4 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <strong>导航</strong>
              <button type="button" aria-label="关闭" onClick={() => setOpen(false)}>
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex flex-col gap-1">
              {items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-orange-50 text-orange-600' : 'text-slate-700 hover:bg-slate-50'}`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        </div>
      )}
      {passwordOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl">
            <h2 className="text-lg font-semibold text-slate-900">修改密码</h2>
            <label className="mt-4 mb-1 block text-xs text-slate-500" htmlFor="old-password">
              原密码
            </label>
            <input
              id="old-password"
              type="password"
              value={oldPassword}
              onChange={(event) => setOldPassword(event.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-500"
            />
            <label className="mt-3 mb-1 block text-xs text-slate-500" htmlFor="new-password">
              新密码
            </label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-500"
            />
            {passwordError && <p className="mt-2 text-sm text-red-600">{passwordError}</p>}
            {passwordHint && <p className="mt-2 text-sm text-emerald-600">{passwordHint}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setPasswordOpen(false)}>
                关闭
              </Button>
              <Button onClick={() => void submitPassword()}>保存</Button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
