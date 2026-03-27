-- BioChat users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Sessions linked to users
CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3 preset accounts: demo/demo123, admin/admin123, researcher/research123
INSERT INTO users (username, password_hash, display_name) VALUES
    ('demo', '$2b$12$kIfkhaFSv4SzkN7q8rumjeJFlzJcb9M3CcHmn341TymFigxFJotXG', 'Demo User'),
    ('admin', '$2b$12$gidG850dtFszl2HDVqr9AeNmKK4EPIWrDx95RZ.8snwmn7A5u7KoG', 'Admin'),
    ('researcher', '$2b$12$ARb3filIMLnDK0AAoIlGTestZ4AKe873qmOXSV//SA0tQ.nZnvKVu', 'Researcher')
ON CONFLICT (username) DO NOTHING;
