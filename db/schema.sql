-- KidsControl schema reference (v1.0)
-- Authoritative creation is via SQLAlchemy app.db.init_db()

CREATE TABLE children (
  id INTEGER PRIMARY KEY,
  slug VARCHAR NOT NULL UNIQUE,
  display_name VARCHAR NOT NULL,
  timezone VARCHAR NOT NULL,
  active BOOLEAN NOT NULL,
  warn_minutes INTEGER NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE devices (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  name VARCHAR NOT NULL,
  device_key VARCHAR NOT NULL UNIQUE,
  os_family VARCHAR NOT NULL,
  hostname VARCHAR,
  last_seen_at DATETIME,
  created_at DATETIME NOT NULL,
  ssh_enabled BOOLEAN NOT NULL DEFAULT 0,
  ssh_host VARCHAR,
  ssh_port INTEGER NOT NULL DEFAULT 22,
  ssh_user VARCHAR,
  ssh_key_path VARCHAR
);

CREATE TABLE schedules (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  weekday INTEGER NOT NULL,
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL,
  daily_minutes INTEGER NOT NULL,
  CONSTRAINT uq_schedule_child_weekday UNIQUE (child_id, weekday)
);

CREATE TABLE app_rules (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  label VARCHAR NOT NULL,
  pattern VARCHAR NOT NULL,
  match_mode VARCHAR NOT NULL,
  enabled BOOLEAN NOT NULL,
  scope VARCHAR NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE overrides (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  grant_until DATETIME NOT NULL,
  grant_type VARCHAR NOT NULL,
  created_by VARCHAR NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE day_overrides (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  day VARCHAR NOT NULL,
  enabled BOOLEAN NOT NULL,
  updated_at DATETIME NOT NULL,
  CONSTRAINT uq_day_override_child_day UNIQUE (child_id, day)
);

CREATE TABLE daily_usage (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  day VARCHAR NOT NULL,
  used_minutes INTEGER NOT NULL,
  last_seen_at DATETIME NOT NULL,
  CONSTRAINT uq_daily_usage_child_day UNIQUE (child_id, day)
);

CREATE TABLE software_watches (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  package_name VARCHAR NOT NULL,
  label VARCHAR NOT NULL,
  CONSTRAINT uq_watch_child_package UNIQUE (child_id, package_name)
);

CREATE TABLE software_items (
  id INTEGER PRIMARY KEY,
  device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  package_name VARCHAR NOT NULL,
  version VARCHAR NOT NULL,
  source VARCHAR NOT NULL,
  reported_at DATETIME NOT NULL,
  CONSTRAINT uq_software_device_package UNIQUE (device_id, package_name)
);

CREATE TABLE pending_updates (
  id INTEGER PRIMARY KEY,
  device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  package_name VARCHAR NOT NULL,
  installed_version VARCHAR NOT NULL,
  available_version VARCHAR NOT NULL,
  source VARCHAR NOT NULL,
  reported_at DATETIME NOT NULL,
  CONSTRAINT uq_pending_device_package UNIQUE (device_id, package_name)
);

CREATE TABLE device_commands (
  id INTEGER PRIMARY KEY,
  device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  kind VARCHAR NOT NULL,
  package_name VARCHAR,
  status VARCHAR NOT NULL,
  via VARCHAR NOT NULL,
  output VARCHAR,
  created_at DATETIME NOT NULL,
  finished_at DATETIME
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  at DATETIME NOT NULL,
  actor VARCHAR NOT NULL,
  child_slug VARCHAR,
  action VARCHAR NOT NULL,
  details VARCHAR
);
