import axios from 'axios';
import type { QuoteTemperature } from '@/lib/types';
import { getTelUrl } from '@/lib/utils';

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

// Company Settings API functions
export const getCompanySettings = async () => {
  const response = await api.get('/api/settings/company');
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
  deposit_amount?: number;
  items: Array<{
    product_id?: number;
    description: string;
    quantity: number;
    unit_price: number;
    is_custom?: boolean;
    sort_order?: number;
  }>;
  discount_template_ids?: number[];
  temperature?: QuoteTemperature;
}) => {
  const response = await api.post('/api/quotes', quoteData);
  return response.data;
};

export const getQuotes = async () => {
  const response = await api.get('/api/quotes');
  return response.data;
};

export const getQuote = async (quoteId: number) => {
  const response = await api.get(`/api/quotes/${quoteId}`);
  return response.data;
};

export const updateDraftQuote = async (quoteId: number, quoteData: {
  valid_until?: string;
  terms_and_conditions?: string;
  notes?: string;
  deposit_amount?: number;
  items: Array<{
    product_id?: number;
    description: string;
    quantity: number;
    unit_price: number;
    is_custom?: boolean;
    sort_order?: number;
    parent_index?: number;
  }>;
  discount_template_ids?: number[];
  temperature?: QuoteTemperature;
}) => {
  const response = await api.put(`/api/quotes/${quoteId}/draft`, quoteData);
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

export const getProduct = async (productId: number) => {
  const response = await api.get(`/api/products/${productId}`);
  return response.data;
};

export const createProduct = async (productData: {
  name: string;
  description?: string;
  category: string;
  subcategory?: string;
  is_extra?: boolean;
  base_price: number;
  unit?: string;
  sku?: string;
  image_url?: string;
  specifications?: string;
  installation_hours?: number;
  boxes_per_product?: number;
  optional_extras?: number[];
}) => {
  const response = await api.post('/api/products', productData);
  return response.data;
};

export const updateProduct = async (productId: number, productData: {
  name?: string;
  description?: string;
  category?: string;
  subcategory?: string;
  is_extra?: boolean;
  base_price?: number;
  unit?: string;
  sku?: string;
  image_url?: string;
  specifications?: string;
  installation_hours?: number;
  boxes_per_product?: number;
  optional_extras?: number[];
  is_active?: boolean;
}) => {
  const response = await api.patch(`/api/products/${productId}`, productData);
  return response.data;
};

export const deleteProduct = async (productId: number) => {
  const response = await api.delete(`/api/products/${productId}`);
  return response.data;
};

export const uploadProductImage = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/api/products/upload-image', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data.image_url;
};

export const getOptionalExtras = async () => {
  const response = await api.get('/api/products/optional-extras');
  return response.data;
};

export const getProductOptionalExtras = async (productId: number) => {
  const response = await api.get(`/api/products/${productId}/optional-extras`);
  return response.data;
};

export const addOptionalExtraToProduct = async (productId: number, extraId: number) => {
  const response = await api.post(`/api/products/${productId}/optional-extras?extra_id=${extraId}`);
  return response.data;
};

export const removeOptionalExtraFromProduct = async (productId: number, extraId: number) => {
  const response = await api.delete(`/api/products/${productId}/optional-extras/${extraId}`);
  return response.data;
};

// Reminder API functions
export const getReminders = async (params?: {
  dismissed?: boolean;
  priority?: string;
  reminder_type?: string;
}) => {
  const response = await api.get('/api/reminders', { params });
  return response.data;
};

export const getStaleSummary = async () => {
  const response = await api.get('/api/reminders/stale-summary');
  return response.data;
};

export const dismissReminder = async (reminderId: number, reason?: string) => {
  const response = await api.post(`/api/reminders/${reminderId}/dismiss`, { reason });
  return response.data;
};

export const actOnReminder = async (reminderId: number, actionTaken: string, notes?: string) => {
  const response = await api.post(`/api/reminders/${reminderId}/act`, {
    action_taken: actionTaken,
    notes,
  });
  return response.data;
};

export const generateReminders = async () => {
  const response = await api.post('/api/reminders/generate');
  return response.data;
};

// Customer History API functions
export const getCustomerHistory = async (customerId: number) => {
  const response = await api.get(`/api/customers/${customerId}/history`);
  return response.data;
};

/** Log a call activity for the customer (no dialer). */
export const logCallActivity = async (
  customerId: number,
  notes?: string
): Promise<void> => {
  await api.post(`/api/customers/${customerId}/activities`, {
    activity_type: 'CALL_ATTEMPTED',
    notes: notes || undefined,
  });
};

/** Log a call activity and open the tel: URL (dialer). */
export const logCallAndOpenTel = async (
  customerId: number,
  phone: string,
  onSuccess?: () => void,
  notes?: string
): Promise<void> => {
  await api.post(`/api/customers/${customerId}/activities`, {
    activity_type: 'CALL_ATTEMPTED',
    notes: notes || undefined,
  });
  onSuccess?.();
  const telUrl = getTelUrl(phone);
  if (telUrl && typeof window !== 'undefined') {
    window.location.href = telUrl;
  }
};

/** Create a manual reminder for a customer (e.g. call back). */
export const createManualReminder = async (data: {
  customer_id: number;
  title: string;
  message: string;
  reminder_date: string; // YYYY-MM-DD
}) => {
  const response = await api.post('/api/reminders', data);
  return response.data;
};

// Discount Template API functions
export const getDiscountTemplates = async (isActive?: boolean) => {
  const params = isActive !== undefined ? { is_active: isActive } : {};
  const response = await api.get('/api/discounts', { params });
  return response.data;
};

export const getDiscountTemplate = async (discountId: number) => {
  const response = await api.get(`/api/discounts/${discountId}`);
  return response.data;
};

export const createDiscountTemplate = async (templateData: {
  name: string;
  description?: string;
  discount_type: string;
  discount_value: number;
  scope: string;
  is_giveaway?: boolean;
}) => {
  const response = await api.post('/api/discounts', templateData);
  return response.data;
};

export const updateDiscountTemplate = async (discountId: number, templateData: {
  name?: string;
  description?: string;
  discount_type?: string;
  discount_value?: number;
  scope?: string;
  is_active?: boolean;
  is_giveaway?: boolean;
}) => {
  const response = await api.patch(`/api/discounts/${discountId}`, templateData);
  return response.data;
};

export const deleteDiscountTemplate = async (discountId: number) => {
  const response = await api.delete(`/api/discounts/${discountId}`);
  return response.data;
};

export const applyDiscountToQuote = async (quoteId: number, templateId: number) => {
  const response = await api.post(`/api/quotes/${quoteId}/discounts?template_id=${templateId}`);
  return response.data;
};

// Discount requests
export const getDiscountRequestsForQuote = async (quoteId: number) => {
  const response = await api.get(`/api/quotes/${quoteId}/discount-requests`);
  return response.data;
};

export const getDiscountRequests = async (params?: { status?: string; quote_id?: number }) => {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set('status', params.status);
  if (params?.quote_id != null) searchParams.set('quote_id', String(params.quote_id));
  const qs = searchParams.toString();
  const url = qs ? `/api/discount-requests?${qs}` : '/api/discount-requests';
  const response = await api.get(url);
  return response.data;
};

export const createDiscountRequest = async (
  quoteId: number,
  body: { discount_type: string; discount_value: number; scope: string; reason?: string }
) => {
  const response = await api.post(`/api/quotes/${quoteId}/discount-requests`, body);
  return response.data;
};

export const approveDiscountRequest = async (requestId: number) => {
  const response = await api.patch(`/api/discount-requests/${requestId}/approve`);
  return response.data;
};

export const rejectDiscountRequest = async (requestId: number, rejectionReason?: string) => {
  const response = await api.patch(`/api/discount-requests/${requestId}/reject`, {
    rejection_reason: rejectionReason ?? undefined,
  });
  return response.data;
};
