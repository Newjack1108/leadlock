import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 second timeout for all requests
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
  template_id?: number;
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

// Email Template API functions
export const getEmailTemplates = async () => {
  const response = await api.get('/api/email-templates');
  return response.data;
};

export const getEmailTemplate = async (templateId: number) => {
  const response = await api.get(`/api/email-templates/${templateId}`);
  return response.data;
};

export const createEmailTemplate = async (templateData: {
  name: string;
  description?: string;
  subject_template: string;
  body_template: string;
  is_default?: boolean;
}) => {
  const response = await api.post('/api/email-templates', templateData);
  return response.data;
};

export const updateEmailTemplate = async (templateId: number, templateData: {
  name?: string;
  description?: string;
  subject_template?: string;
  body_template?: string;
  is_default?: boolean;
}) => {
  const response = await api.put(`/api/email-templates/${templateId}`, templateData);
  return response.data;
};

export const deleteEmailTemplate = async (templateId: number) => {
  const response = await api.delete(`/api/email-templates/${templateId}`);
  return response.data;
};

export const previewEmailTemplate = async (templateId: number, previewData?: {
  customer_id?: number;
}) => {
  const response = await api.post(`/api/email-templates/${templateId}/preview`, previewData || {});
  return response.data;
};

// User Email Settings API functions
export const getUserEmailSettings = async () => {
  const response = await api.get('/api/settings/user/email');
  return response.data;
};

export const updateUserEmailSettings = async (settingsData: {
  smtp_host?: string;
  smtp_port?: number;
  smtp_user?: string;
  smtp_password?: string;
  smtp_use_tls?: boolean;
  smtp_from_email?: string;
  smtp_from_name?: string;
  imap_host?: string;
  imap_port?: number;
  imap_user?: string;
  imap_password?: string;
  imap_use_ssl?: boolean;
  email_signature?: string;
  email_test_mode?: boolean;
}) => {
  const response = await api.put('/api/settings/user/email', settingsData);
  return response.data;
};

// Quote API functions
export const createQuote = async (quoteData: {
  customer_id: number;
  quote_number?: string;
  version?: number;
  valid_until?: string;
  terms_and_conditions?: string;
  notes?: string;
  items: Array<{
    product_id?: number;
    description: string;
    quantity: number;
    unit_price: number;
    is_custom?: boolean;
    sort_order?: number;
  }>;
}) => {
  const response = await api.post('/api/quotes', quoteData);
  return response.data;
};

export const getQuote = async (quoteId: number) => {
  const response = await api.get(`/api/quotes/${quoteId}`);
  return response.data;
};

export const getCustomerQuotes = async (customerId: number) => {
  const response = await api.get(`/api/quotes/customers/${customerId}`);
  return response.data;
};

export const previewQuotePdf = async (quoteId: number) => {
  const response = await api.get(`/api/quotes/${quoteId}/preview-pdf`, {
    responseType: 'blob',
  });
  const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
  window.open(url, '_blank');
  // Clean up the URL after a delay
  setTimeout(() => window.URL.revokeObjectURL(url), 100);
};

export const getProducts = async () => {
  const response = await api.get('/api/products');
  return response.data;
};
