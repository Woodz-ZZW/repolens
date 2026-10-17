BEGIN;

-- 100,000 fake runs
INSERT INTO runs (
    started_at, question, repo_dir, repo_fingerprint, model,
    model_calls, tool_calls_used, elapsed_seconds, trace, usage, run_file
)
SELECT now() - i * interval '1 minute',
       'fake question ' || i,
       '/fake',
       md5(i::text),
       'fake-model',
       1, 1,
       random() * 10,
       '[]', '[]',
       'fake-' || i
FROM generate_series(1, 100000) AS i;

-- Update the statistics the planner uses to choose a plan
ANALYZE runs;

-- Before: no index on repo_fingerprint
EXPLAIN ANALYZE
SELECT id, started_at FROM runs WHERE repo_fingerprint = md5('500');

CREATE INDEX runs_repo_fingerprint_idx ON runs (repo_fingerprint);

-- After: same query
EXPLAIN ANALYZE
SELECT id, started_at FROM runs WHERE repo_fingerprint = md5('500');

-- Before: newest 10 runs (this is the query list_runs uses)
EXPLAIN ANALYZE
SELECT id FROM runs ORDER BY started_at DESC LIMIT 10;

CREATE INDEX runs_started_at_idx ON runs (started_at);

-- After
EXPLAIN ANALYZE
SELECT id FROM runs ORDER BY started_at DESC LIMIT 10;

ROLLBACK;