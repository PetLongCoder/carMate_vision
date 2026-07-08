import axios from 'axios';
import type { ApiResponse } from '../types';
import { AuthError, type AuthErrorCode } from '../utils/authError';

type ApiErrorBody = ApiResponse<unknown> & { authErrorCode?: AuthErrorCode };

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

request.interceptors.response.use(
  (response) => {
    const res = response.data as ApiErrorBody;
    if (res.code !== 200 && res.code !== 0) {
      if (res.authErrorCode) {
        return Promise.reject(new AuthError(res.message, res.authErrorCode));
      }
      console.error(`[API Error] ${res.message}`);
      return Promise.reject(new Error(res.message || '请求失败'));
    }
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    const detail = error.response?.data?.detail;
    if (error.response?.status === 422 && Array.isArray(detail)) {
      const msg = detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('；');
      if (msg) {
        return Promise.reject(new Error(msg));
      }
    }
    return Promise.reject(error);
  },
);

export default request;
