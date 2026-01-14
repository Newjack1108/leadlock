import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// Email API functions
export const sendEmail = async (emailData: {
  customer_id: number;
  to_email: string;
  cc?: string;
  bcc?: string;
  subject: string;
  body_html?: string;
  body_text?: string;
}) => {
  const response = await api.post('/api/emails', emailData);
  return response.data;
};

export const getCustomerEmails = async (customerId: number) => {
  const response = await api.get(`/api/emails/customers/${customerId}`);
  return response.data;
};

export const getEmail = async (emailId: number) => {
  const response = await api.get(`/api/emails/${emailId}`);
  return response.data;
};

export const replyToEmail = async (emailId: number, replyData: {
  body_html?: string;
  body_text?: string;
  cc?: string;
  bcc?: string;
}) => {
  const response = await api.post(`/api/emails/${emailId}/reply`, replyData);
  return response.data;
};

export const getEmailThread = async (emailId: number) => {
  const response = await api.get(`/api/emails/${emailId}/thread`);
  return response.data;
};

export const sendQuoteEmail = async (quoteId: number, emailData: {
  template_id?: number;
  to_email: string;
  cc?: string;
  bcc?: string;
  custom_message?: string;
}) => {
  const response = await api.post(`/api/quotes/${quoteId}/send-email`, emailData);
  return response.data;
};
