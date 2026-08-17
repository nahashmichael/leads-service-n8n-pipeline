CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    first_name TEXT,
    last_name TEXT,
    company TEXT,
    source TEXT CHECK (source IN ('apollo', 'apify')),
    raw_payload TEXT,
    email_valid INTEGER,
    score INTEGER,
    status TEXT NOT NULL DEFAULT 'new',
    icebreaker TEXT,
    reply_text TEXT,
    reply_intent TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads (email);
