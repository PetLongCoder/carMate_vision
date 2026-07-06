/** 常用邮箱格式：用户名@域名.后缀（后缀至少 2 位字母） */
export const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$/;

export function isValidEmail(email: string): boolean {
  const trimmed = email.trim();
  if (!trimmed || trimmed.length > 254) return false;
  if (trimmed.includes('..')) return false;
  return EMAIL_REGEX.test(trimmed);
}

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
