-- INNER JOIN: only runs that have evidence
SELECT r.id, r.status, e.path, e.start_line, e.end_line
FROM runs r
JOIN evidence e ON e.run_id = r.id
ORDER BY r.id;

-- LEFT JOIN: every run, including runs with 0 evidence
SELECT r.id, r.status, count(e.id) AS evidence_count
FROM runs r
LEFT JOIN evidence e ON e.run_id = r.id
GROUP BY r.id
ORDER BY r.id;

-- The files cited most often
SELECT path, count(*) FROM evidence GROUP BY path ORDER BY count(*) DESC;

-- Foreign key: this fails because run 9999 doesn't exist
INSERT INTO evidence (run_id, path, start_line, end_line, code) VALUES (9999, 'x.py', 1, 1, 'x');

-- ON DELETE CASCADE: deleting a run also deletes its evidence
SELECT count(*) FROM evidence WHERE run_id = 1;
DELETE FROM runs WHERE id = 1;
SELECT count(*) FROM evidence WHERE run_id = 1;