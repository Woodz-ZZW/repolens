import { useEffect, useState } from "react";
import { getRun, type Loadable, type Report, type Run } from "./api";

export default function RunDetail({ runId }: { runId: number }) {
  const [run, setRun] = useState<Loadable<Run>>({ state: "loading" });

  useEffect(() => {
    let ignore = false;
    setRun({ state: "loading" });
    getRun(runId)
      .then((data) => {
        if (!ignore) setRun({ state: "ready", data });
      })
      .catch((error: Error) => {
        if (!ignore) setRun({ state: "error", message: error.message });
      });
    return () => {
      ignore = true;
    };
  }, [runId]);

  if (run.state === "loading") return <p className="muted">Loading run #{runId}…</p>;
  if (run.state === "error") return <p className="error">Could not load run #{runId}: {run.message}</p>;

  const { data } = run;
  return (
    <article>
      <h2>Run #{data.id}</h2>
      <p className="muted">
        {new Date(data.started_at).toLocaleString()} · {data.model} · {data.elapsed_seconds}s ·{" "}
        {data.tool_calls_used} tool calls
      </p>
      <h3>Question</h3>
      <p>{data.question}</p>
      {data.report ? (
        <ReportView report={data.report} />
      ) : (
        <p className="error">Diagnosis failed: {data.error}</p>
      )}
    </article>
  );
}

function ReportView({ report }: { report: Report }) {
  return (
    <>
      <h3>
        {report.status === "hypothesis" ? "Root-cause hypothesis (unverified)" : "Insufficient evidence"}
      </h3>
      <p>{report.summary}</p>
      {report.root_cause && (
        <p>
          <strong>Root cause:</strong> {report.root_cause}
        </p>
      )}
      <h3>Evidence</h3>
      {report.evidence.length === 0 && <p className="muted">No code evidence</p>}
      {report.evidence.map((item, index) => (
        <div key={index}>
          <code>
            {item.path}:{item.start_line}-{item.end_line}
          </code>
          <pre>{item.code}</pre>
        </div>
      ))}
      <h3>Suggestion</h3>
      <p>{report.suggestion}</p>
      <TextList title="Verification steps (not run yet)" items={report.verification} />
      <TextList title="Missing information" items={report.missing_information} />
    </>
  );
}

function TextList({ title, items }: { title: string; items: string[] }) {
  return (
    <>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted">None</p>
      ) : (
        <ul>
          {items.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      )}
    </>
  );
}