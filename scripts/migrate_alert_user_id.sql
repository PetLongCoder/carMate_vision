-- ============================================================
-- 告警记录表：添加 user_id 字段，支持按用户隔离告警
-- 执行前请备份数据库
-- ============================================================

-- 1. 添加 user_id 列（允许 NULL，系统级告警不关联用户）
ALTER TABLE alert_records
ADD COLUMN user_id INT NULL COMMENT '关联用户 ID，系统级告警为 NULL';

-- 2. 为 user_id 创建索引（加速按用户过滤查询）
CREATE INDEX idx_alert_records_user_id ON alert_records(user_id);

-- 3. 验证
-- SELECT COUNT(*) FROM alert_records WHERE user_id IS NOT NULL;
-- 预期返回 0（所有现有告警都是系统级，user_id 为 NULL）
