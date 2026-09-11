-- =============================================
-- DialogSpyBot - Full Supabase Schema
-- Run this in Supabase → SQL Editor
-- =============================================

-- 1. Business connections
CREATE TABLE IF NOT EXISTS connections (
    connection_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL
);

-- 2. User settings
CREATE TABLE IF NOT EXISTS user_settings (
    user_id BIGINT PRIMARY KEY,
    language TEXT DEFAULT 'ru',
    show_first_name BOOLEAN DEFAULT TRUE,
    show_last_name  BOOLEAN DEFAULT TRUE,
    show_username   BOOLEAN DEFAULT TRUE,
    show_user_id    BOOLEAN DEFAULT TRUE,
    threaded_mode   BOOLEAN DEFAULT FALSE,
    save_media_mode TEXT DEFAULT 'all'
);

-- 3. Forum topics (threaded mode)
CREATE TABLE IF NOT EXISTS user_topics (
    owner_id         BIGINT NOT NULL,
    business_chat_id BIGINT NOT NULL,
    thread_id        BIGINT NOT NULL,
    topic_name       TEXT,
    PRIMARY KEY (owner_id, business_chat_id)
);

-- 4. Message cache
CREATE TABLE IF NOT EXISTS messages (
    chat_id           BIGINT NOT NULL,
    message_id        BIGINT NOT NULL,
    sender_id         BIGINT,
    sender_username   TEXT,
    sender_first_name TEXT,
    sender_last_name  TEXT,
    content_type      TEXT,
    text_content      TEXT,
    file_id           TEXT,
    PRIMARY KEY (chat_id, message_id)
);

-- 5. Deleted messages log (for statistics)
CREATE TABLE IF NOT EXISTS deleted_messages (
    id                BIGSERIAL PRIMARY KEY,
    owner_user_id     BIGINT NOT NULL,
    from_user_id      BIGINT,
    from_username     TEXT,
    from_first_name   TEXT,
    message_text      TEXT,
    media_type        TEXT,
    media_file_id     TEXT,
    chat_id           BIGINT,
    original_message_id BIGINT,
    deleted_at        TIMESTAMP DEFAULT NOW()
);

-- 6. Edited messages log (for statistics)
CREATE TABLE IF NOT EXISTS edited_messages (
    id              BIGSERIAL PRIMARY KEY,
    owner_user_id   BIGINT NOT NULL,
    from_user_id    BIGINT,
    from_username   TEXT,
    from_first_name TEXT,
    original_text   TEXT,
    new_text        TEXT,
    chat_id         BIGINT,
    message_id      BIGINT,
    edited_at       TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_messages_chat    ON messages(chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_deleted_owner    ON deleted_messages(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_edited_owner     ON edited_messages(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_conn_user        ON connections(user_id);

-- 7. Allowlist (faqat admin ruxsat berganlar)
CREATE TABLE IF NOT EXISTS allowed_users (
    user_id  BIGINT PRIMARY KEY,
    added_by BIGINT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 8. Per-owner message isolation
ALTER TABLE messages ADD COLUMN IF NOT EXISTS owner_id BIGINT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS connection_id TEXT;
UPDATE messages SET owner_id = 0 WHERE owner_id IS NULL;

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_pkey;
ALTER TABLE messages ADD PRIMARY KEY (owner_id, chat_id, message_id);

CREATE INDEX IF NOT EXISTS idx_messages_owner ON messages(owner_id, chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_allowed_users ON allowed_users(user_id);

ALTER TABLE messages ADD COLUMN IF NOT EXISTS local_path TEXT;