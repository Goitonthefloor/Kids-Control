CREATE TABLE children (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	display_name VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
);
CREATE TABLE schedules (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	weekday INTEGER NOT NULL, 
	start_min INTEGER NOT NULL, 
	end_min INTEGER NOT NULL, 
	daily_minutes INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_schedule_user_weekday UNIQUE (username, weekday)
);
CREATE TABLE overrides (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	grant_until DATETIME NOT NULL, 
	grant_type VARCHAR NOT NULL, 
	created_by VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE audit_log (
	id INTEGER NOT NULL, 
	at DATETIME NOT NULL, 
	actor VARCHAR NOT NULL, 
	child VARCHAR, 
	action VARCHAR NOT NULL, 
	details VARCHAR, 
	PRIMARY KEY (id)
);
CREATE TABLE child_policy (
	username VARCHAR NOT NULL, 
	after_expiry_mode VARCHAR NOT NULL, 
	hard_lock BOOLEAN NOT NULL, 
	warn_minutes INTEGER NOT NULL, 
	PRIMARY KEY (username)
);
CREATE TABLE prewarn_log (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	day VARCHAR NOT NULL, 
	mode VARCHAR NOT NULL, 
	shown_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_prewarn_user_day_mode UNIQUE (username, day, mode)
);
CREATE TABLE daily_usage (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	day VARCHAR NOT NULL, 
	used_minutes INTEGER NOT NULL, 
	last_seen_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_daily_usage_user_day UNIQUE (username, day)
);
CREATE TABLE day_overrides (
	username VARCHAR NOT NULL, 
	day VARCHAR NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (username)
);
