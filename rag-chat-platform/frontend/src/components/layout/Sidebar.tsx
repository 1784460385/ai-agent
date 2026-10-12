import { ApiKeyCard } from '../settings/ApiKeyCard';

interface Props {
  saved: boolean;
  modelName: string;
  onSave: (key: string, modelName: string) => void;
}

export function Sidebar({ saved, modelName, onSave }: Props) {
  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto bg-slate-900 px-4 py-5 text-slate-100">
      <div>
        <p className="mb-2 px-1 text-xs font-medium tracking-wider text-slate-400 uppercase">API 设置</p>
        <ApiKeyCard saved={saved} modelName={modelName} onSave={onSave} />
      </div>
    </div>
  );
}
