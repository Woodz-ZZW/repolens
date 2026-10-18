import { useEffect, useState } from "react";
import { listRuns, type Loadable, type RunSummary } from "./api";

interface Props {
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export default function RunList({ selectedId, onSelect }: Props) {
  const [runs, setRuns] = useState<Loadable<RunSummary[]>>({ state: "loading" });

  useEffect(() => {
    listRuns()
      .then((data) => setRuns({ state: "ready", data }))
      .catch((error: Error) => setRuns({ state: "error", message: error.message }));
  }, []);

  if (runs.state === "loading") return <p className="muted">Loading runs…</p>;
  if (runs.state === "error") return <p className="error">Could not load runs: {runs.message}</p>;
  if (runs.data.length === 0) return <p className="muted">No runs yet. Submit a question to create one.</p>;

  return (
    <ul className="run-list">
      {runs.data.map((run) => (
        <li key={run.id}>
          <button
            type="button"
            aria-current={run.id === selectedId}
            onClick={() => onSelect(run.id)}
          >
            <strong>#{run.id}</strong> {run.status ?? "failed"}
            <br />
            <span className="muted">{run.question.slice(0, 60)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}