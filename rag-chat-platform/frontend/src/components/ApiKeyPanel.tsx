import { useState } from 'react';

interface Props {
  onSave: (key: string, modelName: string) => void;
  saved: boolean;
  modelName: string;
}

const MODELS = ['deepseek-flash', 'deepseek-chat', 'deepseek-reasoner'];

export function ApiKeyPanel({ onSave, saved, modelName }: Props) {
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
    setHint('已保存在本次页面会话中，刷新后需要重新输入');
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>DeepSeek API Key</h2>
        <span className={saved ? 'pill pill-on' : 'pill'}>{saved ? '已设置' : '未设置'}</span>
      </div>
      <p className="panel-note">Key 只随本次提问发送，后端不保存。</p>
      <label className="field-label" htmlFor="api-key">
        API Key
      </label>
      <input
        id="api-key"
        type="password"
        value={key}
        onChange={(event) => setKey(event.target.value)}
        placeholder="sk-xxxxxxxxxxxxxxxx"
        autoComplete="off"
      />
      <label className="field-label" htmlFor="model-name">
        模型
      </label>
      <select id="model-name" value={model} onChange={(event) => setModel(event.target.value)}>
        {MODELS.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      <button type="button" className="btn btn-primary" onClick={handleSave}>
        保存
      </button>
      {hint && <p className="hint">{hint}</p>}
    </section>
  );
}
