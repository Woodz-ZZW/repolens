import { useState } from "react";
import type { Run } from "./api";
import DiagnoseForm from "./DiagnoseForm";
import RunDetail from "./RunDetail";
import RunList from "./RunList";

export default function App() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [listVersion, setListVersion] = useState(0);

  function handleCreated(run: Run) {
    setSelectedId(run.id);
    setListVersion((version) => version + 1);
  }

  return (
    <div className="page">
      <h1>RepoLens</h1>
      <div className="layout">
        <aside className="card">
          <h2>Saved runs</h2>
          <RunList key={listVersion} selectedId={selectedId} onSelect={setSelectedId} />
        </aside>
        <main>
          <section className="card">
            <DiagnoseForm onCreated={handleCreated} />
          </section>
          {selectedId !== null && (
            <section className="card">
              <RunDetail runId={selectedId} />
            </section>
          )}
        </main>
      </div>
    </div>
  );
}