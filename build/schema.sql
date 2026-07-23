PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS municipalities (
  id INTEGER PRIMARY KEY,
  prefecture_code TEXT NOT NULL,
  prefecture_name TEXT NOT NULL,
  municipality_code TEXT,
  municipality_name TEXT NOT NULL,
  municipality_type TEXT NOT NULL,
  official_site_url TEXT NOT NULL,
  population INTEGER,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(prefecture_name, municipality_name)
);

CREATE TABLE IF NOT EXISTS life_events (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  source_type TEXT NOT NULL,
  title TEXT,
  url TEXT NOT NULL UNIQUE,
  domain TEXT,
  municipality_id INTEGER,
  fetched_at TEXT,
  http_status INTEGER,
  content_hash TEXT,
  raw_text_path TEXT,
  last_modified_header TEXT,
  etag TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (municipality_id) REFERENCES municipalities(id)
);

CREATE TABLE IF NOT EXISTS source_snapshots (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL,
  fetched_at TEXT NOT NULL,
  content_hash TEXT,
  title TEXT,
  extracted_text_path TEXT,
  diff_summary TEXT,
  FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS candidate_pages (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  municipality_id INTEGER NOT NULL,
  title TEXT,
  detected_life_events TEXT,
  detected_keywords TEXT,
  page_type_guess TEXT,
  confidence_score INTEGER NOT NULL DEFAULT 0,
  crawl_source TEXT,
  status TEXT NOT NULL DEFAULT 'candidate',
  source_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (municipality_id) REFERENCES municipalities(id),
  FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS programs (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  normalized_title TEXT,
  program_type TEXT NOT NULL,
  summary TEXT,
  plain_summary TEXT,
  target_description TEXT,
  benefit_description TEXT,
  amount_min INTEGER,
  amount_max INTEGER,
  amount_text TEXT,
  application_required INTEGER,
  online_available TEXT,
  status TEXT NOT NULL DEFAULT 'unknown',
  starts_on TEXT,
  ends_on TEXT,
  deadline_text TEXT,
  official_url TEXT NOT NULL,
  source_id INTEGER,
  reliability_status TEXT NOT NULL DEFAULT 'auto_extracted',
  last_verified_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(title, official_url),
  FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS program_municipalities (
  id INTEGER PRIMARY KEY,
  program_id INTEGER NOT NULL,
  municipality_id INTEGER NOT NULL,
  area_scope TEXT NOT NULL,
  local_office_name TEXT,
  local_contact TEXT,
  local_url TEXT,
  notes TEXT,
  FOREIGN KEY (program_id) REFERENCES programs(id),
  FOREIGN KEY (municipality_id) REFERENCES municipalities(id),
  UNIQUE(program_id, municipality_id)
);

CREATE TABLE IF NOT EXISTS program_life_events (
  id INTEGER PRIMARY KEY,
  program_id INTEGER NOT NULL,
  life_event_id INTEGER NOT NULL,
  relevance_score INTEGER NOT NULL DEFAULT 50,
  display_reason TEXT,
  FOREIGN KEY (program_id) REFERENCES programs(id),
  FOREIGN KEY (life_event_id) REFERENCES life_events(id),
  UNIQUE(program_id, life_event_id)
);

CREATE TABLE IF NOT EXISTS program_facts (
  id INTEGER PRIMARY KEY,
  program_id INTEGER NOT NULL,
  fact_type TEXT NOT NULL,
  value TEXT NOT NULL,
  evidence_text TEXT,
  evidence_url TEXT NOT NULL,
  evidence_heading TEXT,
  confidence_score INTEGER NOT NULL DEFAULT 60,
  extraction_method TEXT NOT NULL DEFAULT 'manual_research',
  reviewed_status TEXT NOT NULL DEFAULT 'needs_review',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (program_id) REFERENCES programs(id)
);

CREATE TABLE IF NOT EXISTS required_documents (
  id INTEGER PRIMARY KEY,
  program_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  is_required INTEGER NOT NULL DEFAULT 1,
  obtain_from TEXT,
  document_url TEXT,
  FOREIGN KEY (program_id) REFERENCES programs(id)
);

CREATE TABLE IF NOT EXISTS application_steps (
  id INTEGER PRIMARY KEY,
  program_id INTEGER NOT NULL,
  step_number INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  office_name TEXT,
  office_url TEXT,
  online_url TEXT,
  FOREIGN KEY (program_id) REFERENCES programs(id)
);

CREATE TABLE IF NOT EXISTS program_changes (
  id INTEGER PRIMARY KEY,
  program_id INTEGER NOT NULL,
  change_type TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  summary TEXT,
  detected_at TEXT NOT NULL,
  reviewed_by TEXT,
  reviewed_at TEXT,
  FOREIGN KEY (program_id) REFERENCES programs(id)
);

CREATE TABLE IF NOT EXISTS update_runs (
  id INTEGER PRIMARY KEY,
  run_type TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  checked_count INTEGER NOT NULL DEFAULT 0,
  changed_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS program_update_metadata (
  program_id INTEGER PRIMARY KEY,
  update_priority TEXT NOT NULL DEFAULT 'B',
  update_frequency_days INTEGER NOT NULL DEFAULT 45,
  next_check_at TEXT,
  last_checked_at TEXT,
  last_content_change_at TEXT,
  last_fact_reviewed_at TEXT,
  watch_level TEXT NOT NULL DEFAULT 'key_facts',
  watch_fields TEXT NOT NULL DEFAULT '["target","amount","deadline","application","condition","move_value"]',
  update_reason TEXT,
  update_status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (program_id) REFERENCES programs(id)
);

CREATE TABLE IF NOT EXISTS source_update_metadata (
  source_id INTEGER PRIMARY KEY,
  update_priority TEXT NOT NULL DEFAULT 'B',
  check_frequency_days INTEGER NOT NULL DEFAULT 45,
  next_check_at TEXT,
  last_checked_at TEXT,
  last_content_hash TEXT,
  last_http_status INTEGER,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  change_status TEXT NOT NULL DEFAULT 'unknown',
  update_reason TEXT,
  update_status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS source_change_reviews (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL,
  old_content_hash TEXT,
  new_content_hash TEXT,
  detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  diff_summary TEXT,
  impact_level TEXT NOT NULL DEFAULT 'unknown',
  review_status TEXT NOT NULL DEFAULT 'needs_review',
  reviewer_note TEXT,
  reviewed_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (source_id) REFERENCES sources(id),
  UNIQUE(source_id, new_content_hash)
);

CREATE TABLE IF NOT EXISTS update_review_queue (
  id INTEGER PRIMARY KEY,
  queue_type TEXT NOT NULL,
  priority TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id INTEGER NOT NULL,
  municipality_id INTEGER,
  title TEXT,
  url TEXT,
  reason TEXT,
  due_at TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (municipality_id) REFERENCES municipalities(id),
  UNIQUE(queue_type, object_type, object_id, due_at)
);

CREATE TABLE IF NOT EXISTS seo_pages (
  id INTEGER PRIMARY KEY,
  page_type TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  meta_description TEXT,
  municipality_id INTEGER,
  life_event_id INTEGER,
  canonical_url TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  last_generated_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (municipality_id) REFERENCES municipalities(id),
  FOREIGN KEY (life_event_id) REFERENCES life_events(id)
);

CREATE TABLE IF NOT EXISTS known_gaps (
  id INTEGER PRIMARY KEY,
  municipality_id INTEGER NOT NULL,
  life_event_id INTEGER,
  gap_type TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (municipality_id) REFERENCES municipalities(id),
  FOREIGN KEY (life_event_id) REFERENCES life_events(id)
);

CREATE INDEX IF NOT EXISTS idx_programs_type_status ON programs(program_type, status);
CREATE INDEX IF NOT EXISTS idx_programs_reliability ON programs(reliability_status);
CREATE INDEX IF NOT EXISTS idx_program_facts_program ON program_facts(program_id);
CREATE INDEX IF NOT EXISTS idx_program_facts_type ON program_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_sources_municipality ON sources(municipality_id);
CREATE INDEX IF NOT EXISTS idx_candidate_pages_status ON candidate_pages(status);
CREATE INDEX IF NOT EXISTS idx_program_life_events_life_event ON program_life_events(life_event_id);
CREATE INDEX IF NOT EXISTS idx_program_municipalities_municipality ON program_municipalities(municipality_id);
CREATE INDEX IF NOT EXISTS idx_program_update_next ON program_update_metadata(update_status, next_check_at, update_priority);
CREATE INDEX IF NOT EXISTS idx_source_update_next ON source_update_metadata(update_status, next_check_at, update_priority);
CREATE INDEX IF NOT EXISTS idx_update_review_queue_status ON update_review_queue(status, priority, due_at);
