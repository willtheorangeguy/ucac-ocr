CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, year INTEGER NOT NULL, month INTEGER NOT NULL, mode TEXT NOT NULL,
 template TEXT NOT NULL, template_hash TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
 revision INTEGER NOT NULL DEFAULT 1, exported_revision INTEGER NOT NULL DEFAULT 0,
 created REAL NOT NULL, updated REAL NOT NULL, diagnostic TEXT, coverage_ack INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sources(
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), hash TEXT NOT NULL,
 filename TEXT NOT NULL, path TEXT NOT NULL, normalized TEXT, state TEXT DEFAULT 'pending',
 assigned_date TEXT, date_confirmed INTEGER DEFAULT 0, observed_date TEXT, section TEXT, geometry TEXT, version INTEGER DEFAULT 1,
 UNIQUE(job_id,hash));
CREATE TABLE IF NOT EXISTS pages(
 id INTEGER PRIMARY KEY, source_id TEXT REFERENCES sources(id), version INTEGER, section TEXT,
 geometry TEXT, transform TEXT, path TEXT, UNIQUE(source_id,version,section));
CREATE TABLE IF NOT EXISTS tasks(
 id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id), source_id TEXT REFERENCES sources(id),
 key TEXT UNIQUE, version INTEGER, pass TEXT, crop TEXT, expected TEXT,
 state TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, content_failures INTEGER DEFAULT 0,
 availability_failures INTEGER DEFAULT 0, next_at REAL DEFAULT 0, owner TEXT,
 smaller INTEGER DEFAULT 0, result TEXT, latest_chunk REAL);
CREATE TABLE IF NOT EXISTS attempts(
 id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id), owner TEXT, started REAL,
 finished REAL, status TEXT, raw_path TEXT, profile TEXT, model TEXT, model_digest TEXT,
 prompt_version TEXT, schema_version TEXT, preprocessing_version TEXT, error TEXT, metrics TEXT);
CREATE TABLE IF NOT EXISTS readings(
 task_id INTEGER REFERENCES tasks(id), cell_key TEXT, reading TEXT NOT NULL,
 PRIMARY KEY(task_id,cell_key));
CREATE TABLE IF NOT EXISTS cells(
 job_id TEXT REFERENCES jobs(id), key TEXT, date TEXT, time TEXT, column_name TEXT,
 value INTEGER, kind TEXT, status TEXT, provenance TEXT, reviewed INTEGER DEFAULT 0,
 PRIMARY KEY(job_id,key));
CREATE TABLE IF NOT EXISTS issues(
 id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id), key TEXT, kind TEXT, detail TEXT,
 source_id TEXT REFERENCES sources(id), cell_key TEXT, resolved INTEGER DEFAULT 0,
 UNIQUE(job_id,key));
CREATE TABLE IF NOT EXISTS decisions(
 id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id), issue_id INTEGER, cell_key TEXT,
 action TEXT, value INTEGER, note TEXT, reviewer TEXT, created REAL);
CREATE TABLE IF NOT EXISTS exports(
 id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id), revision INTEGER, path TEXT,
 checksum TEXT, draft INTEGER, created REAL, report TEXT, recalculated INTEGER DEFAULT 0,
 UNIQUE(job_id,revision));
CREATE TABLE IF NOT EXISTS worker_owner(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), generation TEXT, heartbeat REAL,
 active_task INTEGER, cooldown_until REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS task_queue ON tasks(state,next_at,job_id,source_id,id);
