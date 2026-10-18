import { useState, type FormEvent } from "react";
import { createRun, type Run } from "./api";

export default function DiagnoseForm({ onCreated }: { onCreated: (run: Run) => void }) {
  const [question, setQuestion] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const run = await createRun(question, apiKey);
      setQuestion("");
      onCreated(run);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2>New diagnosis</h2>
      <label htmlFor="question">Problem description</label>
      <textarea
        id="question"
        rows={5}
        maxLength={4000}
        required
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
      />
      <label htmlFor="api-key">API key</label>
      <input
        id="api-key"
        type="password"
        required
        value={apiKey}
        onChange={(event) => setApiKey(event.target.value)}
      />
      <button type="submit" disabled={pending}>
        {pending ? "Diagnosing… (this can take a minute)" : "Diagnose"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}