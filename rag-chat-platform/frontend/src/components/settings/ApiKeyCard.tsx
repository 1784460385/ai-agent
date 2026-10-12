import { useState } from 'react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

const MODELS = ['deepseek-flash', 'deepseek-chat', 'deepseek-reasoner'];

interface Props {
  saved: boolean;
  modelName: string;
  onSave: (key: string, modelName: string) => void;
}

export function ApiKeyCard({ saved, modelName, onSave }: Props) {
  const [key, setKey] = useState('');
  const [model, setModel] = useState(modelName);
  const [hint, setHint] = useState('');

  const handleSave = () => {
    const next = key.trim();
    if (!next.startsWith('sk-')) {
      setHint('API Key 应以 sk- 开头');
      return;
    }
    onSave(next, model);
    setKey('');
    setHint('只对当前登录账号有效，切换账号后需要重新填写');
  };

  return (
    <section id="api-settings" className="rounded-xl bg-slate-800 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-slate-100">DeepSeek API Key</h2>
        <Badge dot={saved ? 'on' : 'off'}>{saved ? '已设置' : '未设置'}</Badge>
      </div>
      <p className="mb-3 text-xs leading-5 text-slate-400">Key 只随本次提问发送，后端不保存。</p>
      <label className="mb-1 block text-xs text-slate-400" htmlFor="api-key">
        API Key
      </label>
      <input
        id="api-key"
        type="password"
        value={key}
        autoComplete="off"
        placeholder="sk-xxxxxxxxxxxxxxxx"
        onChange={(event) => setKey(event.target.value)}
        className="mb-3 w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-orange-500"
      />
      <label className="mb-1 block text-xs text-slate-400" htmlFor="model-name">
        模型
      </label>
      <select
        id="model-name"
        value={model}
        onChange={(event) => setModel(event.target.value)}
        className="mb-3 w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-orange-500"
      >
        {MODELS.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      <Button className="w-full" onClick={handleSave} aria-label="保存 API Key">
        保存
      </Button>
      {hint && <p className="mt-2 text-xs leading-5 text-slate-400">{hint}</p>}
    </section>
  );
}
