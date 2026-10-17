-- 5 slowest runs
SELECT id, model, status, elapsed_seconds
FROM runs
ORDER BY elapsed_seconds DESC
LIMIT 5;

-- Error rate per model (FILTER = count only some rows)
SELECT model,
       count(*) AS runs,
       count(*) FILTER (WHERE error IS NOT NULL) AS errors,
       round(100.0 * count(*) FILTER (WHERE error IS NOT NULL) / count(*), 1) AS error_pct
FROM runs
GROUP BY model;

-- Share of each status (window function: sum over all groups)
SELECT status,
       count(*) AS runs,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM runs
GROUP BY status
ORDER BY runs DESC;

-- Repo versions diagnosed more than once (HAVING = WHERE for groups)
SELECT repo_fingerprint, count(*) AS runs
FROM runs
GROUP BY repo_fingerprint
HAVING count(*) > 1;

-- Total tokens per run (unpack the usage JSONB array into rows)
SELECT r.id, sum((u->>'total_tokens')::int) AS total_tokens
FROM runs r, jsonb_array_elements(r.usage) AS u
GROUP BY r.id
ORDER BY total_tokens DESC;

-- Latest run for each question
SELECT DISTINCT ON (question) question, id, status, started_at
FROM runs
ORDER BY question, started_at DESC;

-- Search inside the report
SELECT id, report->>'root_cause' AS root_cause
FROM runs
WHERE report->>'root_cause' ILIKE '%threshold%';

-- Runs from the last 7 days
SELECT id, started_at, status
FROM runs
WHERE started_at >= now() - interval '7 days'
ORDER BY started_at DESC;