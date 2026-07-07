import request from './request';
import { isValidEmail } from '../utils/validation';
import { AuthError } from '../utils/authError';
import type {
  ApiResponse,
  AuthResponse,
  LoginRequest,
  RegisterRequest,
  User,
  PhoneLoginRequest,
  EmailLoginRequest,
  SendSmsCodeRequest,
  SendEmailCodeRequest,
  VerifySmsCodeRequest,
} from '../types';

const USE_MOCK = import.meta.env.VITE_USE_MOCK_AUTH !== 'false';

const MOCK_USERS_KEY = 'carmate_mock_users';
const MOCK_CODES_KEY = 'carmate_mock_codes';
const CODE_TTL_MS = 5 * 60 * 1000;

interface MockUserRecord extends User {
  password: string;
}

interface MockCodeRecord {
  target: string;
  code: string;
  expiresAt: number;
}

function getMockUsers(): MockUserRecord[] {
  const raw = localStorage.getItem(MOCK_USERS_KEY);
  if (raw) {
    return JSON.parse(raw) as MockUserRecord[];
  }

  const defaults: MockUserRecord[] = [
    {
      id: 1,
      username: 'admin',
      password: '123456',
      role: 'admin',
      phone: '13900139000',
      email: 'admin@example.com',
    },
    {
      id: 2,
      username: 'user',
      password: '123456',
      role: 'user',
      phone: '13800138000',
      email: 'user@example.com',
    },
  ];
  localStorage.setItem(MOCK_USERS_KEY, JSON.stringify(defaults));
  return defaults;
}

function saveMockUsers(users: MockUserRecord[]) {
  localStorage.setItem(MOCK_USERS_KEY, JSON.stringify(users));
}

function getMockCodes(): MockCodeRecord[] {
  const raw = sessionStorage.getItem(MOCK_CODES_KEY);
  return raw ? (JSON.parse(raw) as MockCodeRecord[]) : [];
}

function saveMockCode(target: string, code: string) {
  const codes = getMockCodes().filter((item) => item.target !== target);
  codes.push({ target, code, expiresAt: Date.now() + CODE_TTL_MS });
  sessionStorage.setItem(MOCK_CODES_KEY, JSON.stringify(codes));
}

function verifyMockCode(target: string, code: string) {
  const record = getMockCodes().find((item) => item.target === target);
  if (!record) throw new Error('请先获取验证码');
  if (Date.now() > record.expiresAt) throw new Error('验证码已过期，请重新获取');
  if (record.code !== code) throw new Error('验证码错误');
}

function generateCode() {
  return String(Math.floor(100000 + Math.random() * 900000));
}

function toAuthResponse(user: User): AuthResponse {
  return {
    token: `mock-token-${user.role}-${user.id}`,
    user,
  };
}

function findByPhone(phone: string) {
  return getMockUsers().find((u) => u.phone === phone);
}

function findByEmail(email: string) {
  return getMockUsers().find((u) => u.email === email);
}

function mockLogin(data: LoginRequest): AuthResponse {
  const users = getMockUsers();
  const found = users.find((u) => u.username === data.username);

  if (!found) {
    throw new AuthError('该用户名未注册，请先注册', 'NOT_REGISTERED');
  }

  if (found.password !== data.password) {
    throw new Error('密码错误');
  }

  const { password: _, ...user } = found;
  return toAuthResponse(user);
}

function mockRegister(data: RegisterRequest): AuthResponse {
  const reserved = ['admin'];
  if (reserved.includes(data.username.toLowerCase())) {
    throw new Error('该用户名不可注册');
  }

  if (!/^1[3-9]\d{9}$/.test(data.phone)) {
    throw new Error('请输入正确的手机号');
  }

  verifyMockCode(`phone:${data.phone}`, data.code);

  const users = getMockUsers();
  if (users.some((u) => u.username === data.username)) {
    throw new AuthError('该用户名已注册，请前往登录', 'ALREADY_REGISTERED');
  }
  if (users.some((u) => u.phone === data.phone)) {
    throw new AuthError('该手机号已注册，请前往登录', 'ALREADY_REGISTERED');
  }
  if (data.email && users.some((u) => u.email === data.email)) {
    throw new AuthError('该邮箱已注册，请前往登录', 'ALREADY_REGISTERED');
  }
  if (data.email && !isValidEmail(data.email)) {
    throw new Error('请输入正确的邮箱格式，如 user@example.com');
  }

  const newUser: MockUserRecord = {
    id: Date.now(),
    username: data.username,
    password: data.password,
    phone: data.phone,
    email: data.email,
    role: 'user',
  };
  users.push(newUser);
  saveMockUsers(users);

  const { password: _, ...user } = newUser;
  return toAuthResponse(user);
}

function mockSendSmsCode(data: SendSmsCodeRequest) {
  if (!/^1[3-9]\d{9}$/.test(data.phone)) {
    throw new Error('请输入正确的手机号');
  }

  const exists = !!findByPhone(data.phone);

  if (data.scene === 'login' && !exists) {
    throw new AuthError('该手机号未注册，请先注册', 'NOT_REGISTERED');
  }

  if (data.scene === 'register' && exists) {
    throw new AuthError('该手机号已注册，请前往登录', 'ALREADY_REGISTERED');
  }

  const code = generateCode();
  saveMockCode(`phone:${data.phone}`, code);
  return code;
}

function mockSendEmailCode(data: SendEmailCodeRequest) {
  if (!isValidEmail(data.email)) {
    throw new Error('请输入正确的邮箱格式，如 user@example.com');
  }

  const exists = !!findByEmail(data.email);

  if (data.scene === 'login' && !exists) {
    throw new AuthError('该邮箱未注册，请先注册', 'NOT_REGISTERED');
  }

  if (data.scene === 'register' && exists) {
    throw new AuthError('该邮箱已注册，请前往登录', 'ALREADY_REGISTERED');
  }

  const code = generateCode();
  saveMockCode(`email:${data.email}`, code);
  return code;
}

function mockLoginByPhone(data: PhoneLoginRequest): AuthResponse {
  verifyMockCode(`phone:${data.phone}`, data.code);

  const found = findByPhone(data.phone);
  if (!found) {
    throw new AuthError('该手机号未注册，请先注册', 'NOT_REGISTERED');
  }

  if (found.role !== 'user') {
    throw new Error('管理员请使用账号密码登录');
  }

  const { password: _, ...user } = found;
  return toAuthResponse(user);
}

function mockLoginByEmail(data: EmailLoginRequest): AuthResponse {
  verifyMockCode(`email:${data.email}`, data.code);

  const found = findByEmail(data.email);
  if (!found) {
    throw new AuthError('该邮箱未注册，请先注册', 'NOT_REGISTERED');
  }

  if (found.role !== 'user') {
    throw new Error('管理员请使用账号密码登录');
  }

  const { password: _, ...user } = found;
  return toAuthResponse(user);
}

export async function login(data: LoginRequest): Promise<AuthResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400));
    return mockLogin(data);
  }

  const res = await request.post<ApiResponse<AuthResponse>>('/auth/login', data);
  return res.data.data;
}

export async function register(data: RegisterRequest): Promise<AuthResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400));
    return mockRegister(data);
  }

  const res = await request.post<ApiResponse<AuthResponse>>('/auth/register', data);
  return res.data.data;
}

export async function sendSmsCode(data: SendSmsCodeRequest): Promise<void> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400));
    const code = mockSendSmsCode(data);
    if (import.meta.env.DEV) {
      console.info(`[Mock SMS] ${data.phone} 验证码: ${code}`);
    }
    return;
  }

  await request.post<ApiResponse<null>>('/auth/sms/send', data);
}

export async function verifySmsCode(data: VerifySmsCodeRequest): Promise<void> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400));
    verifyMockCode(`phone:${data.phone}`, data.code);
    return;
  }

  await request.post<ApiResponse<null>>('/auth/sms/verify', data);
}

export async function sendEmailCode(data: SendEmailCodeRequest): Promise<void> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400));
    const code = mockSendEmailCode(data);
    if (import.meta.env.DEV) {
      console.info(`[Mock Email] ${data.email} 验证码: ${code}`);
    }
    return;
  }

  await request.post<ApiResponse<null>>('/auth/email/send', data);
}

export async function loginByPhone(data: PhoneLoginRequest): Promise<AuthResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400));
    return mockLoginByPhone(data);
  }

  const res = await request.post<ApiResponse<AuthResponse>>('/auth/sms/login', data);
  return res.data.data;
}

export async function loginByEmail(data: EmailLoginRequest): Promise<AuthResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400));
    return mockLoginByEmail(data);
  }

  const res = await request.post<ApiResponse<AuthResponse>>('/auth/email/login', data);
  return res.data.data;
}

export async function getCurrentUser(): Promise<User> {
  if (USE_MOCK) {
    const raw = localStorage.getItem('user');
    if (!raw) throw new Error('未登录');
    return JSON.parse(raw) as User;
  }

  const res = await request.get<ApiResponse<User>>('/auth/me');
  return res.data.data;
}

export { AuthError } from '../utils/authError';
