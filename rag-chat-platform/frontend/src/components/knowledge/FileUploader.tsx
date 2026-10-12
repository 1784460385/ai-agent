import type { AppConfig, DepartmentInfo } from '../../api/client';

interface Props {
  departments: DepartmentInfo[];
  config: AppConfig | null;
  value: string;
  disabled?: boolean;
  dragging: boolean;
  onChange: (value: string) => void;
  onFiles: (files: File[]) => void;
  onDragging: (value: boolean) => void;
}

export function FileUploader({
  departments,
  config,
  value,
  disabled,
  dragging,
  onChange,
  onFiles,
  onDragging,
}: Props) {
  const labels = Array.from(new Set((config?.formats ?? []).map((item) => item.label)));
  const officeLimit = config?.formats.find((item) => item.label === 'Word')?.max_mb ?? 50;
  return (
    <div className="space-y-2">
      <label className="block text-xs text-slate-400" htmlFor="upload-department">
        导入到
      </label>
      <select
        id="upload-department"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-orange-500"
      >
        {departments.map((dept) => (
          <option key={dept.key} value={dept.key}>
            {dept.name}
          </option>
        ))}
      </select>
      <label
        className={`block cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
          dragging ? 'border-orange-500 bg-orange-500/10' : 'border-slate-600 hover:border-orange-500'
        }`}
        onDragOver={(event) => {
          event.preventDefault();
          onDragging(true);
        }}
        onDragLeave={() => onDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          onDragging(false);
          onFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <input
          type="file"
          accept={config?.accept ?? '.pdf,.docx,.xlsx,.pptx,.md,.txt'}
          multiple
          disabled={disabled}
          className="hidden"
          aria-label="选择知识库文档"
          onChange={(event) => {
            const selected = event.target.files ? Array.from(event.target.files) : [];
            event.target.value = '';
            onFiles(selected);
          }}
        />
        <strong className="block text-sm text-slate-100">{disabled ? '正在上传…' : '拖入或选择文档'}</strong>
        <span className="mt-1 block text-xs text-slate-400">
          支持 {labels.length ? labels.join(' / ') : 'PDF / Word / Excel / PPT'}，Office 文档不超过 {officeLimit}MB
        </span>
        {config?.coming_soon?.length ? (
          <span className="mt-1 block text-xs text-slate-500">{config.coming_soon.join('、')} 即将支持</span>
        ) : null}
      </label>
    </div>
  );
}
