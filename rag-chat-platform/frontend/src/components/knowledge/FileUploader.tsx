import { Upload } from 'lucide-react';
import type { AppConfig } from '../../api/client';

interface Props {
  config: AppConfig | null;
  folderName?: string;
  disabled?: boolean;
  dragging: boolean;
  onFiles: (files: File[]) => void;
  onDragging: (value: boolean) => void;
}

export function FileUploader({ config, folderName, disabled, dragging, onFiles, onDragging }: Props) {
  const labels = Array.from(new Set((config?.formats ?? []).map((item) => item.label)));
  const officeLimit = config?.formats.find((item) => item.label === 'Word')?.max_mb ?? 50;
  const imageLimit = config?.image_max_mb ?? config?.formats.find((item) => item.label === '图片')?.max_mb ?? 20;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
      <label
        className={`flex h-36 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 text-center transition-colors ${
          dragging ? 'border-orange-500 bg-orange-500/10' : 'border-slate-600 hover:border-orange-500'
        } ${disabled ? 'pointer-events-none opacity-60' : ''}`}
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
          accept={config?.accept ?? '.pdf,.docx,.xlsx,.pptx,.md,.txt,.jpg,.jpeg,.png,.webp'}
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
        <Upload className={`mb-2 h-5 w-5 ${dragging ? 'text-orange-400' : 'text-slate-400'}`} />
        <strong className="block text-sm font-semibold text-slate-100">
          {disabled ? '正在上传…' : folderName ? `拖入文件到「${folderName}」` : '拖入或选择文档'}
        </strong>
        <span className="mt-1 block text-xs text-slate-400">
          支持 {labels.length ? labels.join(' / ') : 'PDF / Word / Excel / PPT / 图片'}，Office ≤ {officeLimit}MB，图片 ≤ {imageLimit}MB
        </span>
        {config?.ocr_enabled !== false ? (
          <span className="mt-1 block text-xs text-slate-500">图片与扫描件将自动 OCR，耗时可能较长</span>
        ) : null}
        {config?.coming_soon?.length ? (
          <span className="mt-1 block text-xs text-slate-500">{config.coming_soon.join('、')} 即将支持</span>
        ) : null}
      </label>
    </div>
  );
}
