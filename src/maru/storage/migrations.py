SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS arcs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    state TEXT NOT NULL,
    current_agent TEXT,
    next_step TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    arc_id TEXT NOT NULL REFERENCES arcs(id),
    description TEXT NOT NULL,
    state TEXT NOT NULL,
    depends_on TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    arc_id TEXT NOT NULL REFERENCES arcs(id),
    run_id TEXT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    artifact_refs TEXT NOT NULL,
    parent_event_id TEXT
);

CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    arc_id TEXT NOT NULL REFERENCES arcs(id),
    role TEXT NOT NULL,
    backend TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    exit_code INTEGER
);

CREATE TABLE IF NOT EXISTS gates (
    id TEXT PRIMARY KEY,
    arc_id TEXT NOT NULL REFERENCES arcs(id),
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    path TEXT PRIMARY KEY,
    arc_id TEXT NOT NULL REFERENCES arcs(id),
    run_id TEXT,
    kind TEXT NOT NULL
);
"""

