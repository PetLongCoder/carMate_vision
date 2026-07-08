-- 已有 users 表时执行，为微信登录(Mock)增加字段
USE carmate;

ALTER TABLE users ADD COLUMN wechat_openid VARCHAR(64) UNIQUE;
ALTER TABLE users ADD COLUMN wechat_unionid VARCHAR(64) UNIQUE;
ALTER TABLE users ADD COLUMN nickname VARCHAR(64);
ALTER TABLE users ADD COLUMN avatar_url VARCHAR(255);
