import { useState } from "react";
import { X } from "lucide-react";

interface Props {
  agents: string[];
  onSubmit: (title: string, description: string, planner?: string, implementer?: string, reviewer?: string, coordinator?: string) => void;
  onCancel: () => void;
}

export default function CardForm({ agents, onSubmit, onCancel }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [coordinator, setCoordinator] = useState("");
  const [planner, setPlanner] = useState("");
  const [implementer, setImplementer] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [delegateToAI, setDelegateToAI] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !description.trim()) return;
    if (delegateToAI) {
      onSubmit(title.trim(), description.trim(), undefined, undefined, undefined, coordinator || undefined);
    } else {
      onSubmit(
        title.trim(),
        description.trim(),
        planner || undefined,
        implementer || undefined,
        reviewer || undefined,
        coordinator || undefined,
      );
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 mb-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-zinc-300">New Task</span>
        <button type="button" onClick={onCancel} className="text-zinc-500 hover:text-zinc-300 transition-colors">
          <X size={14} />
        </button>
      </div>

      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 mb-2"
        autoFocus
      />

      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description"
        rows={3}
        className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 mb-2 resize-none"
      />

      <label className="flex items-center gap-2 mb-2 cursor-pointer">
        <input
          type="checkbox"
          checked={delegateToAI}
          onChange={(e) => setDelegateToAI(e.target.checked)}
          className="rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
        />
        <span className="text-xs text-zinc-400">Delegate to AI</span>
      </label>

      <div className="space-y-1.5 mb-2">
        <RoleSelect label="Coordinator" value={coordinator} onChange={setCoordinator} agents={agents} />
        {!delegateToAI && (
          <>
            <RoleSelect label="Planner" value={planner} onChange={setPlanner} agents={agents} />
            <RoleSelect label="Implementer" value={implementer} onChange={setImplementer} agents={agents} />
            <RoleSelect label="Reviewer" value={reviewer} onChange={setReviewer} agents={agents} />
          </>
        )}
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          type="submit"
          disabled={!title.trim() || !description.trim()}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded px-3 py-1.5 text-sm font-medium text-white transition-colors"
        >
          Create Card
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-zinc-400 hover:text-zinc-200 px-3 py-1.5 text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function RoleSelect({ label, value, onChange, agents }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  agents: string[];
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-zinc-500 w-20 shrink-0">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500"
      >
        <option value="">Unassigned</option>
        {agents.map((agent) => (
          <option key={agent} value={agent}>
            {agent}
          </option>
        ))}
      </select>
    </div>
  );
}
