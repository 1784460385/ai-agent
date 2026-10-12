import { KnowledgePanel } from '../components/knowledge/KnowledgePanel';

export function KnowledgePage() {
  return (
    <div className="h-full overflow-y-auto bg-slate-900 text-slate-100">
      <div className="mx-auto max-w-3xl px-4 py-6">
        <KnowledgePanel />
      </div>
    </div>
  );
}
