import type { RouterInfo } from '../../api/client';

export function RouterBadge({ router }: { router: RouterInfo }) {
  const names = router.departments.map((item) => item.name).join('、');
  const via = router.via === 'rule' ? '规则匹配' : '智能识别';
  return (
    <div className="mb-2 inline-flex items-center rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-600">
      已检索：{names || '全部文件夹'} · {via}
    </div>
  );
}
