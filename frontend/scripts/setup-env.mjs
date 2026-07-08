// 首次运行时自动从 .env.example 创建 .env
import { existsSync, copyFileSync } from 'node:fs';

const env = '.env';
const example = '.env.example';

if (!existsSync(env) && existsSync(example)) {
  copyFileSync(example, env);
  console.log('[setup] 已从 .env.example 自动创建 .env，请按需修改配置');
}
