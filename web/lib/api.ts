import axios from 'axios';
import type { QuoteTemperature } from '@/lib/types';
import { getTelUrl } from '@/lib/utils';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000, // 15s - fail fast if API is down
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
}, attachments?: File[]) => {
  const formData = new FormData();
  formData.append('email_data', JSON.stringify(emailData));
  if (attachments?.length) {
    for (const file of attachments) {
      formData.append('attachments', file);
    }
  }
  const response = await api.post('/api/emails', formData);
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
}, attachments?: File[]) => {
  const formData = new FormData();
  formData.append('reply_data', JSON.stringify(replyData));
  if (attachments?.length) {
    for (const file of attachments) {
      formData.append('attachments', file);
    }
  }
  const response = await api.post(`/api/emails/${emailId}/reply`, formData);
  return response.data;
};

export const getEmailThread = async (emailId: number) => {
  const response = await api.get(`/api/emails/${emailId}/thread`);
  return response.data;
};

// SMS API functions
export const sendSms = async (data: {
  customer_id: number;
  to_phone?: string;
  body: string;
  lead_id?: number;
}) => {
  const response = await api.post('/api/sms', data);
  return response.data;
};

export const getCustomerSms = async (customerId: number) => {
  const response = await api.get(`/api/sms/customers/${customerId}`);
  return response.data;
};

export const getUnreadSms = async () => {
  const response = await api.get('/api/dashboard/unread-sms');
  return response.data;
};

export const markCustomerSmsRead = async (customerId: number) => {
  const response = await api.post(`/api/sms/customers/${customerId}/mark-read`);
  return response.data;
};

export const getSms = async (smsId: number) => {
  const response = await api.get(`/api/sms/${smsId}`);
  return response.data;
};

export const createScheduledSms = async (data: {
  customer_id: number;
  to_phone: string;
  body: string;
  scheduled_at: string;
}) => {
  const response = await api.post('/api/sms/scheduled', data);
  return response.data;
};

export const getScheduledSms = async (params?: { customer_id?: number; status?: string }) => {
  const response = await api.get('/api/sms/scheduled', { params });
  return response.data;
};

export const updateScheduledSms = async (id: number, data: { scheduled_at?: string; status?: string }) => {
  const response = await api.patch(`/api/sms/scheduled/${id}`, data);
  return response.data;
};

export const cancelScheduledSms = async (id: number) => {
  const response = await api.delete(`/api/sms/scheduled/${id}`);
  return response.data;
};

// Messenger API functions
export const sendMessengerMessage = async (data: {
  customer_id: number;
  to_psid?: string;
  body: string;
}) => {
  const response = await api.post('/api/messenger', data);
  return response.data;
};

export const getCustomerMessenger = async (customerId: number) => {
  const response = await api.get(`/api/messenger/customers/${customerId}`);
  return response.data;
};

export const markCustomerMessengerRead = async (customerId: number) => {
  const response = await api.post(`/api/messenger/customers/${customerId}/mark-read`);
  return response.data;
};

export const getUnreadMessenger = async () => {
  const response = await api.get('/api/dashboard/unread-messenger');
  return response.data;
};

export const getUnreadCountsByCustomer = async (): Promise<{ customer_id: number; unread_count: number }[]> => {
  const response = await api.get('/api/dashboard/unread-by-customer');
  return response.data;
};

// SMS Template API functions
export const getSmsTemplates = async () => {
  const response = await api.get('/api/sms-templates');
  return response.data;
};

export const getSmsTemplate = async (templateId: number) => {
  const response = await api.get(`/api/sms-templates/${templateId}`);
  return response.data;
};

export const createSmsTemplate = async (data: {
  name: string;
  description?: string;
  body_template: string;
  is_default?: boolean;
}) => {
  const response = await api.post('/api/sms-templates', data);
  return response.data;
};

export const updateSmsTemplate = async (templateId: number, data: {
  name?: string;
  description?: string;
  body_template?: string;
  is_default?: boolean;
}) => {
  const response = await api.put(`/api/sms-templates/${templateId}`, data);
  return response.data;
};

export const deleteSmsTemplate = async (templateId: number) => {
  const response = await api.delete(`/api/sms-templates/${templateId}`);
  return response.data;
};

export const previewSmsTemplate = async (templateId: number, previewData?: {
  customer_id?: number;
}) => {
  const response = await api.post(`/api/sms-templates/${templateId}/preview`, previewData || {});
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

/** Public quote view by token (no auth). Used when customer opens "View your quote" link. */
export const getPublicQuoteView = async (viewToken: string) => {
  const response = await api.get(`/api/public/quotes/view/${viewToken}`);
  return response.data;
};

/** Base URL for API (same as axios baseURL). */
export const getApiBaseUrl = () => process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/** Download quote PDF by public view token (no auth). Triggers browser download. */
export const downloadPublicQuotePdf = async (viewToken: string) => {
  const base = getApiBaseUrl().replace(/\/$/, '');
  const url = `${base}/api/public/quotes/view/${viewToken}/pdf`;
  const response = await fetch(url, { credentials: 'omit' });
  if (!response.ok) throw new Error('Failed to download PDF');
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition');
  let filename = `Quote.pdf`;
  if (disposition) {
    const match = /filename="?([^";\n]+)"?/.exec(disposition);
    if (match) filename = match[1].trim();
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
};

/** Get latest customer view URL for a quote (for testing open tracking). */
export const getQuoteViewLink = async (quoteId: number): Promise<{ view_url: string | null }> => {
  const response = await api.get(`/api/quotes/${quoteId}/view-link`);
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

// Delivery & installation estimate (mileage, travel time, overnight, cost breakdown)
export const estimateDeliveryInstall = async (
  customerPostcode: string,
  installationHours: number,
  numberOfBoxes?: number
) => {
  const response = await api.post('/api/delivery-install/estimate', {
    customer_postcode: customerPostcode,
    installation_hours: installationHours,
    number_of_boxes: numberOfBoxes,
  });
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
    parent_index?: number;
    line_type?: 'DELIVERY' | 'INSTALLATION';
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

export const acceptQuote = async (quoteId: number) => {
  const response = await api.patch(`/api/quotes/${quoteId}`, { status: 'ACCEPTED' });
  return response.data;
};

export const getOrders = async () => {
  const response = await api.get('/api/orders');
  return response.data;
};

export const getOrder = async (orderId: number) => {
  const response = await api.get(`/api/orders/${orderId}`);
  return response.data;
};

export const updateOrder = async (
  orderId: number,
  data: {
    deposit_paid?: boolean;
    balance_paid?: boolean;
    paid_in_full?: boolean;
    installation_booked?: boolean;
    installation_completed?: boolean;
  }
) => {
  const response = await api.patch(`/api/orders/${orderId}`, data);
  return response.data;
};

export const getOrderDepositInvoicePdf = async (orderId: number) => {
  const response = await api.get(`/api/orders/${orderId}/invoice/deposit-pdf`, {
    responseType: 'blob',
  });
  const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Invoice_Deposit_${orderId}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const getOrderPaidInFullInvoicePdf = async (orderId: number) => {
  const response = await api.get(`/api/orders/${orderId}/invoice/paid-in-full-pdf`, {
    responseType: 'blob',
  });
  const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Invoice_PaidInFull_${orderId}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const pushOrderToXero = async (orderId: number) => {
  const response = await api.post(`/api/orders/${orderId}/push-to-xero`);
  return response.data;
};

/** Send access sheet link for order. Returns URL for staff to copy. Auth required. */
export const sendAccessSheet = async (orderId: number): Promise<{
  access_sheet_url: string;
  access_token: string;
}> => {
  const response = await api.post(`/api/orders/${orderId}/access-sheet/send`);
  return response.data;
};

/** Send order to production app as work order. Auth required. */
export const sendOrderToProduction = async (orderId: number): Promise<{ success: boolean; message?: string }> => {
  const response = await api.post(`/api/orders/${orderId}/send-to-production`);
  return response.data;
};

/** Public: Get access sheet form context by token (no auth). */
export const getAccessSheetContext = async (token: string): Promise<{
  customer_name: string;
  order_number: string;
  completed: boolean;
  completed_at?: string | null;
  answers?: Record<string, string> | null;
}> => {
  const response = await api.get(`/api/public/access-sheet/${token}`);
  return response.data;
};

/** Public: Submit access sheet form (no auth). */
export const submitAccessSheet = async (
  token: string,
  data: Record<string, string | undefined | null>
) => {
  const body: Record<string, string> = {};
  for (const [k, v] of Object.entries(data)) {
    if (v != null && v !== '') body[k] = String(v);
  }
  const response = await api.post(`/api/public/access-sheet/${token}`, body);
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
    line_type?: 'DELIVERY' | 'INSTALLATION';
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
