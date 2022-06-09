CREATE TABLE questions (
    id TEXT PRIMARY KEY,
    title TEXT,
    score INT,
    created_utc INT,
    author TEXT,
    permalink TEXT,
    answer TEXT,
    week TEXT
);

CREATE INDEX week_index ON questions(week);

CREATE TABLE comments (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    body TEXT,
    score INT,
    created_utc INT,
    author TEXT
);

CREATE INDEX parent_index ON comments(parent_id);