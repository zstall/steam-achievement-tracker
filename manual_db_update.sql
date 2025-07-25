-- Manual database update script for ActivityFeed table
-- Run this if you want to preserve existing data

-- Create the activity_feed table
CREATE TABLE IF NOT EXISTS activity_feed (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    activity_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    game_id INTEGER REFERENCES games(id),
    custom_achievement_id INTEGER REFERENCES custom_achievements(id),
    shared_achievement_id INTEGER REFERENCES shared_achievements(id),
    activity_metadata JSONB,
    is_public BOOLEAN NOT NULL DEFAULT true,
    is_highlighted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_activity_feed_user_id ON activity_feed(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_feed_created_at ON activity_feed(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_feed_public_recent ON activity_feed(is_public, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_feed_user_recent ON activity_feed(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_feed_type ON activity_feed(activity_type);

-- Verify the table was created
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'activity_feed' 
ORDER BY ordinal_position;