/** 常用邮箱格式：用户名@域名.后缀（后缀至少 2 位字母） */
export const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$/;

/** 密码：8-128 位，须含字母和数字，不能含空格 */
export const PASSWORD_REGEX = /^(?=.*[A-Za-z])(?=.*\d)\S{8,128}$/;

export const PASSWORD_HINT = '8-128 位，须同时包含字母和数字，不能含空格';

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
      if (!value) {
        return required ? Promise.reject(new Error('请输入密码')) : Promise.resolve();
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
        return required ? Promise.reject(new Error('请输入邮箱')) : Promise.resolve();
      }
      if (!isValidEmail(value)) {
        return Promise.reject(new Error('请输入正确的邮箱格式，如 user@example.com'));
      }
      return Promise.resolve();
    },
  });

  return rules;
};
