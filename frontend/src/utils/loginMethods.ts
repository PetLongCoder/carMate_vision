import type { User } from '../types';

/** 与后端 list_login_methods 保持一致；API 未返回时前端自行计算 */
export function resolveLoginMethods(user: User): string[] {
  if (user.login_methods && user.login_methods.length > 0) {
    return user.login_methods;
  }

  const methods: string[] = [];
  const wechatOnly =
    !!user.has_wechat && !user.phone && !user.email && user.username.startsWith('wx_');

  if (!wechatOnly) {
    methods.push('password');
  }
  if (user.phone) {
    methods.push('phone');
  }
  if (user.email) {
    methods.push('email');
  }
  if (user.has_wechat) {
    methods.push('wechat');
  }
  return methods;
}
