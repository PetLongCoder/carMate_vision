import { message, Modal } from 'antd';
import type { NavigateFunction } from 'react-router-dom';
import { isAuthError, getAuthRedirectPath } from './authError';

export function notifyAuthError(err: unknown, navigate: NavigateFunction) {
  if (isAuthError(err)) {
    const redirectPath = getAuthRedirectPath(err.code);
    const isGoLogin = redirectPath === '/login';

    Modal.confirm({
      title: isGoLogin ? '账号已存在' : '账号未注册',
      content: `${err.message}，是否前往${isGoLogin ? '登录' : '注册'}？`,
      okText: isGoLogin ? '去登录' : '去注册',
      cancelText: '留在此页',
      centered: true,
      onOk: () => navigate(redirectPath),
    });
    return;
  }

  if (err instanceof Error && err.message) {
    message.error(err.message);
    return;
  }

  message.error('操作失败，请稍后重试');
}
