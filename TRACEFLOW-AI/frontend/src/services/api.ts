import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001/api/v1';

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const demoRole = localStorage.getItem('tf_demo_role');
  if (demoRole) {
    config.headers['X-Demo-Role'] = demoRole;
  }
  return config;
});
