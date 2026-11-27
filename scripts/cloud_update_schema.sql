CREATE TABLE update_requests (
  request_id TEXT PRIMARY KEY NOT NULL,
  day TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('reserved','active','unknown','done','failed')),
  charged INTEGER NOT NULL CHECK(charged IN (0,1)),
  next_poll INTEGER NOT NULL,
  run_id TEXT,
  result TEXT
);
CREATE INDEX update_requests_day ON update_requests(day);
CREATE UNIQUE INDEX update_requests_single_active ON update_requests((1))
  WHERE state IN ('reserved','active','unknown');
