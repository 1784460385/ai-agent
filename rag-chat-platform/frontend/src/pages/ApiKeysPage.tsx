import { KeyRound, Plus, Star } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  createApiKey,
  deleteApiKey,
  listApiKeys,
  setDefaultApiKey,
  updateApiKey,
  type ApiKeyItem,
} from '../api/client';
import { Button } from '../components/ui/Button';

const MODELS = ['deepseek-flash', 'deepseek-chat', 'deepseek-reasoner'];

const emptyForm = {
  name: '',
  api_key: '',
  model: 'deepseek-flash',
  base_url: 'https://api.deepseek.com',
};

export function ApiKeysPage() {
  const [items, setItems] = useState<ApiKeyItem[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState<ApiKeyItem | null>(null);
  const [creating, setCreating] = useState(true);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const next = await listApiKeys();
    setItems(next);
    return next;
  };

  useEffect(() => {
    load()
      .then((next) => {
        const current = next.find((item) => item.is_default) || next[0];
        if (current) {
          setCreating(false);
          setEditing(current);
          setForm({ name: current.name, api_key: '', model: current.model, base_url: current.base_url });
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : '无法读取配置'));
  }, []);

  const startCreate = () => {
    setCreating(true);
    setEditing(null);
    setForm(emptyForm);
    setError('');
    setNotice('');
  };

  const startEdit = (item: ApiKeyItem) => {
    setCreating(false);
    setEditing(item);
    setForm({ name: item.name, api_key: '', model: item.model, base_url: item.base_url });
    setError('');
    setNotice('');
  };

  const submit = async () => {
    setError('');
    setNotice('');
    const name = form.name.trim();
    const apiKey = form.api_key.trim();
    if (!name) {
      setError('请填写名称');
      return;
    }
    if (creating && !apiKey.startsWith('sk-')) {
      setError('API Key 应以 sk- 开头');
      return;
    }
    if (!creating && apiKey && !apiKey.startsWith('sk-')) {
      setError('API Key 应以 sk- 开头');
      return;
    }
    setSaving(true);
    try {
      if (editing && !creating) {
        const updated = await updateApiKey(editing.id, {
          name,
          api_key: apiKey,
          model: form.model,
          base_url: form.base_url.trim(),
        });
        setNotice('已保存');
        const next = await load();
        const current = next.find((item) => item.id === updated.id) || updated;
        startEdit(current);
        setNotice('已保存');
      } else {
        const created = await createApiKey({
          name,
          api_key: apiKey,
          model: form.model,
          base_url: form.base_url.trim(),
        });
        await load();
        startEdit(created);
        setNotice('已添加');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item: ApiKeyItem) => {
    if (!window.confirm(`删除配置「${item.name}」？`)) return;
    setError('');
    setNotice('');
    try {
      await deleteApiKey(item.id);
      const next = await load();
      const current = next.find((row) => row.is_default) || next[0];
      if (current) startEdit(current);
      else startCreate();
      setNotice('已删除');
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  const makeDefault = async (item: ApiKeyItem) => {
    setError('');
    setNotice('');
    try {
      await setDefaultApiKey(item.id);
      const next = await load();
      const current = next.find((row) => row.id === item.id);
      if (current) startEdit(current);
      setNotice('已设为默认');
    } catch (err) {
      setError(err instanceof Error ? err.message : '设置失败');
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-slate-50">
      <div className="mx-auto flex h-full max-w-6xl flex-col px-6 py-8">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-slate-900">模型配置</h1>
          <p className="mt-1 text-sm text-slate-500">在这里添加和修改 API Key。聊天页顶部的下拉框只用来切换当前使用的配置。</p>
        </div>
        <div className="grid min-h-0 flex-1 gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="rounded-2xl border border-slate-200 bg-white p-3">
            <button
              type="button"
              onClick={startCreate}
              className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl bg-orange-500 px-3 py-2.5 text-sm font-medium text-white hover:bg-orange-600"
            >
              <Plus className="h-4 w-4" />
              新建配置
            </button>
            {items.length === 0 ? (
              <div className="px-3 py-10 text-center text-sm text-slate-400">还没有配置</div>
            ) : (
              <ul className="space-y-2">
                {items.map((item) => {
                  const active = !creating && editing?.id === item.id;
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => startEdit(item)}
                        className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                          active ? 'border-orange-300 bg-orange-50' : 'border-transparent hover:bg-slate-50'
                        }`}
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm font-medium text-slate-900">{item.name}</span>
                          {item.is_default && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2 py-0.5 text-[11px] text-orange-700">
                              <Star className="h-3 w-3" />
                              默认
                            </span>
                          )}
                        </span>
                        <span className="mt-1 block truncate font-mono text-xs text-slate-500">{item.masked_key}</span>
                        <span className="mt-1 block text-xs text-slate-400">{item.model}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>

          <section className="rounded-2xl border border-slate-200 bg-white p-6">
            <div className="mb-5 flex items-start gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-orange-50 text-orange-600">
                <KeyRound className="h-5 w-5" />
              </span>
              <div>
                <h2 className="text-lg font-semibold text-slate-900">{creating ? '新建配置' : '编辑配置'}</h2>
                <p className="mt-1 text-sm text-slate-500">
                  {creating ? '保存后会出现在聊天页的切换列表里。' : '不修改 Key 时把密码框留空。'}
                </p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm text-slate-700">
                名称
                <input
                  value={form.name}
                  aria-label="配置名称"
                  placeholder="例如：DeepSeek 生产号"
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-500"
                />
              </label>
              <label className="block text-sm text-slate-700">
                模型
                <select
                  value={form.model}
                  aria-label="模型"
                  onChange={(event) => setForm({ ...form, model: event.target.value })}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-500"
                >
                  {MODELS.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-slate-700 sm:col-span-2">
                API Key{creating ? '' : '（留空则不修改）'}
                <input
                  type="password"
                  value={form.api_key}
                  autoComplete="off"
                  placeholder={editing && !creating ? editing.masked_key : 'sk-'}
                  aria-label="API Key"
                  onChange={(event) => setForm({ ...form, api_key: event.target.value })}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:ring-2 focus:ring-orange-500"
                />
              </label>
              <label className="block text-sm text-slate-700 sm:col-span-2">
                Base URL
                <input
                  value={form.base_url}
                  aria-label="Base URL"
                  onChange={(event) => setForm({ ...form, base_url: event.target.value })}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-500"
                />
              </label>
            </div>
            {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
            {notice && <p className="mt-4 text-sm text-emerald-600">{notice}</p>}
            <div className="mt-6 flex flex-wrap justify-end gap-2">
              {editing && !creating && !editing.is_default && (
                <Button variant="secondary" onClick={() => void makeDefault(editing)}>
                  设为默认
                </Button>
              )}
              {editing && !creating && (
                <Button variant="danger" onClick={() => void remove(editing)}>
                  删除
                </Button>
              )}
              <Button onClick={() => void submit()} disabled={saving}>
                {saving ? '保存中…' : '保存'}
              </Button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
