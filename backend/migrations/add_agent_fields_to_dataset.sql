-- Migration: Add agent-based architecture fields to datasets table
-- Date: 2025-10-30
-- Purpose: Support MindsDB agent-based chat architecture

-- Add agent tracking fields
ALTER TABLE datasets
ADD COLUMN IF NOT EXISTS agent_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS agent_created_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS agent_last_updated TIMESTAMP,
ADD COLUMN IF NOT EXISTS chat_model_provider VARCHAR(50),
ADD COLUMN IF NOT EXISTS chat_model_config JSONB;

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_datasets_agent_name ON datasets(agent_name);
CREATE INDEX IF NOT EXISTS idx_datasets_chat_model_provider ON datasets(chat_model_provider);

-- Add comments for documentation
COMMENT ON COLUMN datasets.agent_name IS 'MindsDB agent name for this dataset (agent-based architecture)';
COMMENT ON COLUMN datasets.agent_created_at IS 'Timestamp when the MindsDB agent was created';
COMMENT ON COLUMN datasets.agent_last_updated IS 'Timestamp when the agent configuration was last updated';
COMMENT ON COLUMN datasets.chat_model_provider IS 'LLM provider for chat: google, openai, anthropic, azure_openai';
COMMENT ON COLUMN datasets.chat_model_config IS 'Additional model configuration parameters (JSON)';
