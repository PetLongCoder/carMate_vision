/** 常用邮箱格式：用户名@域名.后缀（后缀至少 2 位字母） */
export const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$/;

/** 密码：8-128 位，须含字母和数字，不能含空格（与 backend/app/utils/password_validation.py 保持一致） */
export const PASSWORD_REGEX = /^(?=.*[A-Za-z])(?=.*\d)\S{8,128}$/;

export const PASSWORD_HINT = '8-128 位，须同时包含字母和数字，不能含空格';

export const PASSWORD_CHECKS = [
  { key: 'length', label: '8-128 位', test: (value: string) => value.length >= 8 && value.length <= 128 },
  { key: 'letter', label: '包含字母', test: (value: string) => /[A-Za-z]/.test(value) },
  { key: 'digit', label: '包含数字', test: (value: string) => /\d/.test(value) },
  { key: 'space', label: '不含空格', test: (value: string) => !/\s/.test(value) },
] as const;

export type PasswordStrengthLevel = 'weak' | 'fair' | 'good' | 'strong';

export interface PasswordStrengthResult {
  level: PasswordStrengthLevel;
  label: string;
  percent: number;
  checks: Array<{ key: string; label: string; passed: boolean }>;
}

export function analyzePasswordStrength(password: string): PasswordStrengthResult {
  const checks = PASSWORD_CHECKS.map(({ key, label, test }) => ({
    key,
    label,
    passed: password.length > 0 && test(password),
  }));
  const passedCount = checks.filter((item) => item.passed).length;

  if (!password) {
    return { level: 'weak', label: '弱', percent: 0, checks };
  }

  if (!isValidPassword(password)) {
    const percent = Math.min(25 + passedCount * 15, 50);
    return { level: passedCount <= 1 ? 'weak' : 'fair', label: passedCount <= 1 ? '弱' : '一般', percent, checks };
  }

  if (password.length >= 12 && /[a-z]/.test(password) && /[A-Z]/.test(password)) {
    return { level: 'strong', label: '强', percent: 100, checks };
  }

  return { level: 'good', label: '合格', percent: 75, checks };
}

/** 支持接收验证码的常见邮箱域名（按常用程度排序） */
export const EMAIL_DOMAINS = [
  'qq.com',
  'foxmail.com',
  '163.com',
  '126.com',
  '139.com',
  'yeah.net',
  'sina.com',
  'sohu.com',
  'gmail.com',
  'outlook.com',
  'hotmail.com',
  'live.com',
  'icloud.com',
  'aliyun.com',
  '189.cn',
  '21cn.com',
  'tom.com',
  'vip.sina.com',
  'vip.163.com',
  'vip.126.com',
] as const;

export function isValidEmail(email: string): boolean {
  const trimmed = email.trim();
  if (!trimmed || trimmed.length > 254) return false;
  if (trimmed.includes('..')) return false;
  return EMAIL_REGEX.test(trimmed);
}

export function isValidPassword(password: string): boolean {
  return PASSWORD_REGEX.test(password);
}

export function buildEmailSuggestions(input: string): string[] {
  const trimmed = input.trim();
  const atIndex = trimmed.indexOf('@');
  if (atIndex < 0) return [];

  const local = trimmed.slice(0, atIndex);
  if (!local) return [];

  const domainPart = trimmed.slice(atIndex + 1).toLowerCase();
  const domains = domainPart
    ? EMAIL_DOMAINS.filter((domain) => domain.startsWith(domainPart))
    : [...EMAIL_DOMAINS];

  return domains.map((domain) => `${local}@${domain}`);
}

export const passwordFormRules = (required = true) => {
  const rules: Array<Record<string, unknown>> = [];

  if (required) {
    rules.push({ required: true, message: '请输入密码' });
  }

  rules.push({
    validator(_: unknown, value: string) {
      if (!value || !value.trim()) {
        // 必填时交给 required 规则，避免重复提示
        return Promise.resolve();
      }
      if (!isValidPassword(value)) {
        return Promise.reject(new Error(PASSWORD_HINT));
      }
      return Promise.resolve();
    },
  });

  return rules;
};

export const confirmPasswordRules = (passwordField: string, label = '密码') => [
  { required: true, message: `请再次输入${label}` },
  ({ getFieldValue }: { getFieldValue: (name: string) => string }) => ({
    validator(_: unknown, value: string) {
      if (!value || getFieldValue(passwordField) === value) {
        return Promise.resolve();
      }
      return Promise.reject(new Error('两次密码不一致'));
    },
  }),
];

export const emailFormRules = (required = false) => {
  const rules: Array<Record<string, unknown>> = [];

  if (required) {
    rules.push({ required: true, message: '请输入邮箱' });
  }

  rules.push({
    validator(_: unknown, value: string) {
      if (!value || !value.trim()) {
        // 必填时交给 required 规则，避免重复提示
        return Promise.resolve();
      }
      if (!isValidEmail(value)) {
        return Promise.reject(new Error('请输入正确的邮箱格式，如 user@example.com'));
      }
      return Promise.resolve();
    },
  });

  return rules;
};
