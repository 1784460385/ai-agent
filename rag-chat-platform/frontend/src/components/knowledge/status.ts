import type { DepartmentInfo } from '../../api/client';

export type FolderIndexStatus = 'indexed' | 'pending' | 'indexing';

export function folderIndexStatus(department: DepartmentInfo): FolderIndexStatus {
  if (department.files.some((file) => file.parse_status === 'parsing')) return 'indexing';
  if (!department.files.length || department.chunk_count === 0) return 'pending';
  if (department.files.some((file) => file.parse_status === 'failed')) return 'pending';
  return 'indexed';
}

export function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function fileKind(name: string) {
  return name.split('.').pop()?.toLowerCase() ?? '';
}
