import { useState } from "react";
import { X } from "lucide-react";
import { Button, Input, Select, Switch, Textarea } from "./ui";

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
    <form onSubmit={handleSubmit} className="ui-panel p-3 mb-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-ui">New Task</span>
        <Button type="button" onClick={onCancel} variant="ghost" size="sm" icon={<X size={14} />}><span className="sr-only">Close</span></Button>
      </div>

      <Input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        className="w-full bg-ui-elevated border-ui-strong text-sm text-ui placeholder:text-ui-faint mb-2"
        autoFocus
      />

      <Textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description"
        rows={3}
        className="w-full bg-ui-elevated border-ui-strong text-sm text-ui placeholder:text-ui-faint mb-2 resize-none"
      />

      <label className="flex items-center gap-2 mb-2 cursor-pointer">
        <Switch checked={delegateToAI} onChange={setDelegateToAI} />
        <span className="text-xs text-ui-muted">Delegate to AI</span>
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
        <Button
          type="submit"
          disabled={!title.trim() || !description.trim()}
          className="ui-btn-primary disabled:opacity-40 text-sm font-medium"
        >
          Create Card
        </Button>
        <Button
          type="button"
          onClick={onCancel}
          variant="ghost"
        >
          Cancel
        </Button>
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
      <span className="text-xs text-ui-subtle w-20 shrink-0">{label}</span>
      <Select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 bg-ui-elevated border-ui-strong text-sm text-ui"
      >
        <option value="">Unassigned</option>
        {agents.map((agent) => (
          <option key={agent} value={agent}>
            {agent}
          </option>
        ))}
      </Select>
    </div>
  );
}
