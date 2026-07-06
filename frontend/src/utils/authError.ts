export type AuthErrorCode = 'NOT_REGISTERED' | 'ALREADY_REGISTERED';

export class AuthError extends Error {
  code: AuthErrorCode;

  constructor(message: string, code: AuthErrorCode) {
    super(message);
    this.name = 'AuthError';
    this.code = code;
  }
}

export function isAuthError(err: unknown): err is AuthError {
  return err instanceof AuthError;
}

export function getAuthRedirectPath(code: AuthErrorCode): '/login' | '/register' {
  return code === 'NOT_REGISTERED' ? '/register' : '/login';
}
