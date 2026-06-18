import axios from 'axios';
import type { AxiosRequestConfig } from 'axios';
import {
  ActivityType,
  type CustomerCommunicationStats,
  type DashboardCommunicationTotals,
  type DashboardPresetPeriod,
  type DashboardStats,
  type DateRangeQueryParams,
  type DealerProfile,
  type DealerSummary,
  type AuthMe,
  type ConfiguratorCatalogResponse,
  type ConfiguratorAccessStatus,
  type ConfiguratorPreviewResponse,
  type ConfiguratorInvite,
  type PublicConfiguratorContext,
  type QuoteConfigurationPayload,
  type QuoteConfigurationResponse,
  type DealerDiscountPolicyAdminPayload,
  type DealerDiscountPolicyAdminResponse,
  type DealerAllowedDiscountPolicy,
  type LeadHandoverPdfOptions,
  type OutreachSendListResponse,
  type OutreachSendTargetType,
  type DealerProfileUpdatePayload,
  type DealerQuoteCreatePayload,
  type DealerWelcome,
  type FacebookAdvertProfile,
  type QuoteTemperature,
  type QuoteFulfillmentMethod,
  type QuoteStatus,
  type QuoteListPayload,
  type CustomerListPayload,
  type AutomatedReminderCleanupResult,
  type StaleSummary,
  type WeeklyPlanListResponse,
  type WeeklyPlanRun,
  type WeeklyPlanItem,
  type WeeklyPlanItemStatus,
  type WeeklyPlanTemplate,
  type WeeklyPlanTemplateCreate,
  type WeeklyPlanTemplateUpdate,
  type WeeklyPlanTemplatePreviewResponse,
  type WeeklyPlanBulkSendResult,
} from '@/lib/types';
import { getTelUrl } from '@/lib/utils';
import { resolveApiBaseUrl } from '@/lib/runtimeApiUrl';

declare module 'axios' {
  interface AxiosRequestConfig {
    /**
     * When true, skip the global 401 redirect handler and let the caller
     * decide how to recover from unauthorized responses.
     */
    skipAuthRedirect?: boolean;
  }
}

const api = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 60_000, // Railway public Postgres + cold pool can exceed 15s on first request
});

/** List/auth on Railway public DB can be slow on cold start. */
export const LIST_FETCH_TIMEOUT_MS = 60_000;
export const AUTH_FETCH_TIMEOUT_MS = 60_000;

/** Compose, quote email, reply, heavy quote writes: provider + DB often exceed 15s on Railway */
export const EMAIL_AND_UPLOAD_TIMEOUT_MS = 120_000;

// Add token to requests; resolve API base URL per request (runtime injection from layout).
api.interceptors.request.use((config) => {
  const base = resolveApiBaseUrl();
  if (base) {
    config.baseURL = base;
  }
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
    const requestConfig = (error?.config ?? {}) as AxiosRequestConfig;
    if (error.response?.status === 401 && !requestConfig.skipAuthRedirect) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

/** Readable message from axios / FastAPI (`detail` string or validation array). */
export function getApiErrorDetail(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status;
    const data = err.response?.data;
    if (data && typeof data === 'object' && 'detail' in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === 'string' && detail.trim()) return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((item) => {
            if (typeof item !== 'object' || item === null || !('msg' in item)) {
              return JSON.stringify(item);
            }
            const loc =
              'loc' in item && Array.isArray((item as { loc?: unknown }).loc)
                ? (item as { loc: (string | number)[] }).loc.filter((p) => p !== 'body').join('.')
                : '';
            const msg = String((item as { msg: unknown }).msg);
            return loc ? `${loc}: ${msg}` : msg;
          })
          .join('; ');
      }
    }
    if (typeof data === 'string' && data.trim()) return data;
    if (err.message) {
      if (status && !err.message.includes(String(status))) {
        return `${err.message} (${status})`;
      }
      return err.message;
    }
    if (status) return `Request failed (${status})`;
  }
  if (err instanceof Error && err.message) return err.message;
  return 'Something went wrong';
}

export default api;

function buildDateRangeParams(filter?: DateRangeQueryParams | string): Record<string, string> {
  if (!filter) return {};
  if (typeof filter === 'string') {
    return { period: filter };
  }
  if (filter.start_date && filter.end_date) {
    return {
      start_date: filter.start_date,
      end_date: filter.end_date,
    };
  }
  if (filter.period) {
    return { period: filter.period };
  }
  return {};
}

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
  // Must not set Content-Type when sending FormData - let browser set multipart/form-data with boundary
  const response = await api.post('/api/emails', formData, {
    timeout: EMAIL_AND_UPLOAD_TIMEOUT_MS,
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
  return response.data;
};

export const previewComposeEmail = async (payload: {
  customer_id: number;
  body_html?: string;
  body_text?: string;
  subject?: string;
  to_email?: string;
  cc?: string;
  attachment_filenames?: string[];
}) => {
  const response = await api.post('/api/emails/preview', payload);
  return response.data as { subject?: string | null; body_html: string; to_email?: string | null; cc?: string | null };
};

export const getCustomerEmails = async (customerId: number) => {
  const response = await api.get(`/api/emails/customers/${customerId}`);
  return response.data;
};

export type MessagesMarkReadResult = { marked_count: number; marked_ids: number[] };
export type MessagesMarkUnreadResult = { unmarked_count: number };

export const markCustomerEmailsRead = async (customerId: number): Promise<MessagesMarkReadResult> => {
  const response = await api.post(`/api/emails/customers/${customerId}/mark-read`);
  return response.data;
};

export const markEmailMessagesUnread = async (messageIds: number[]): Promise<MessagesMarkUnreadResult> => {
  const response = await api.post('/api/emails/mark-unread', { message_ids: messageIds });
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
  // Must not set Content-Type when sending FormData - let browser set multipart/form-data with boundary
  const response = await api.post(`/api/emails/${emailId}/reply`, formData, {
    timeout: EMAIL_AND_UPLOAD_TIMEOUT_MS,
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
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

export const markCustomerSmsRead = async (customerId: number): Promise<MessagesMarkReadResult> => {
  const response = await api.post(`/api/sms/customers/${customerId}/mark-read`);
  return response.data;
};

export const markSmsMessagesUnread = async (messageIds: number[]): Promise<MessagesMarkUnreadResult> => {
  const response = await api.post('/api/sms/mark-unread', { message_ids: messageIds });
  return response.data;
};

export const getSms = async (smsId: number) => {
  const response = await api.get(`/api/sms/${smsId}`);
  return response.data;
};

export const pauseCustomerSmsBot = async (customerId: number, minutes = 720) => {
  const response = await api.post(`/api/sms/customers/${customerId}/bot/pause`, null, {
    params: { minutes },
  });
  return response.data as { ok: boolean; customer_id: number; paused_until: string };
};

export const stopCustomerSmsBot = async (customerId: number) => {
  const response = await api.post(`/api/sms/customers/${customerId}/bot/stop`);
  return response.data as { ok: boolean; customer_id: number; sms_bot_stopped: boolean };
};

export const resumeCustomerSmsBot = async (customerId: number) => {
  const response = await api.post(`/api/sms/customers/${customerId}/bot/resume`);
  return response.data as {
    ok: boolean;
    customer_id: number;
    paused_until: null;
    sms_bot_stopped: boolean;
  };
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

export const createScheduledEmail = async (
  emailData: {
    customer_id: number;
    to_email: string;
    cc?: string;
    bcc?: string;
    subject: string;
    body_html?: string;
    body_text?: string;
    scheduled_at: string;
  },
  attachments?: File[]
) => {
  const formData = new FormData();
  formData.append('email_data', JSON.stringify(emailData));
  if (attachments?.length) {
    for (const file of attachments) {
      formData.append('attachments', file);
    }
  }
  const response = await api.post('/api/emails/scheduled', formData, {
    timeout: EMAIL_AND_UPLOAD_TIMEOUT_MS,
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
  return response.data;
};

export const getScheduledEmails = async (params?: { customer_id?: number; status?: string }) => {
  const response = await api.get('/api/emails/scheduled', { params });
  return response.data;
};

export const updateScheduledEmail = async (
  id: number,
  data: { scheduled_at?: string; status?: string }
) => {
  const response = await api.patch(`/api/emails/scheduled/${id}`, data);
  return response.data;
};

export const cancelScheduledEmail = async (id: number) => {
  const response = await api.delete(`/api/emails/scheduled/${id}`);
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

export const markCustomerMessengerRead = async (customerId: number): Promise<MessagesMarkReadResult> => {
  const response = await api.post(`/api/messenger/customers/${customerId}/mark-read`);
  return response.data;
};

export const markMessengerMessagesUnread = async (messageIds: number[]): Promise<MessagesMarkUnreadResult> => {
  const response = await api.post('/api/messenger/mark-unread', { message_ids: messageIds });
  return response.data;
};

/** Dispatched after restoring unread so the header badge updates without a route change. */
export const LEADLOCK_REFRESH_UNREAD_EVENT = 'leadlock:refreshUnreadCounts';

export function dispatchRefreshUnreadCounts(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(LEADLOCK_REFRESH_UNREAD_EVENT));
  }
}

export const getUnreadMessenger = async () => {
  const response = await api.get('/api/dashboard/unread-messenger');
  return response.data;
};

export const getUnreadEmails = async () => {
  const response = await api.get('/api/dashboard/unread-email');
  return response.data;
};

export const getDashboardStats = async (filter?: DateRangeQueryParams): Promise<DashboardStats> => {
  const response = await api.get('/api/dashboard/stats', { params: buildDateRangeParams(filter) });
  return response.data;
};

export const getLeadLocations = async (filter?: DateRangeQueryParams | DashboardPresetPeriod) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/dashboard/lead-locations', { params });
  return response.data;
};

export const getDashboardCommunicationTotals = async (
  filter: DateRangeQueryParams = { period: 'week' }
): Promise<DashboardCommunicationTotals> => {
  const response = await api.get('/api/dashboard/communication-totals', { params: buildDateRangeParams(filter) });
  return response.data;
};

export const getUnreadCountsByCustomer = async (): Promise<{ customer_id: number; unread_count: number }[]> => {
  const response = await api.get('/api/dashboard/unread-by-customer', {
    timeout: LIST_FETCH_TIMEOUT_MS,
  });
  return response.data;
};

export const getCustomers = async (options?: {
  search?: string;
  sms_opted_out?: boolean;
  has_unread?: boolean;
  include_total?: boolean;
  page?: number;
  page_size?: number;
}) => {
  const params: Record<string, string | number | boolean> = {};
  if (options?.search?.trim()) params.search = options.search.trim();
  if (options?.sms_opted_out) params.sms_opted_out = true;
  if (options?.has_unread) params.has_unread = true;
  if (options?.include_total === false) params.includeTotal = false;
  if (options?.page != null) params.page = options.page;
  if (options?.page_size != null) params.page_size = options.page_size;
  const response = await api.get('/api/customers', {
    params: Object.keys(params).length ? params : undefined,
    timeout: LIST_FETCH_TIMEOUT_MS,
  });
  return response.data as CustomerListPayload;
};

export type CustomerUnreadChannels = {
  sms_unread: number;
  messenger_unread: number;
  email_unread: number;
};

export const getCustomerUnreadChannels = async (
  customerId: number
): Promise<CustomerUnreadChannels> => {
  const response = await api.get(`/api/customers/${customerId}/unread-channels`);
  return response.data;
};

export const getCustomerCommunicationStats = async (
  customerId: number
): Promise<CustomerCommunicationStats> => {
  const response = await api.get(`/api/customers/${customerId}/communication-stats`);
  return response.data;
};

export const getQualifiedForQuoting = async (assignedTo?: 'me') => {
  const params = assignedTo ? { assigned_to: assignedTo } : {};
  const response = await api.get('/api/dashboard/qualified-for-quoting', { params });
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

// Sales Documents API functions
export const getSalesDocuments = async (category?: string): Promise<import('@/lib/types').SalesDocument[]> => {
  const params = category ? { category } : {};
  const response = await api.get('/api/sales-documents', { params });
  return response.data;
};

export const uploadSalesDocument = async (file: File, name: string, category?: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', name);
  if (category) formData.append('category', category);
  const response = await api.post('/api/sales-documents', formData, {
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
  return response.data;
};

export const downloadSalesDocument = async (id: number): Promise<Blob> => {
  const response = await api.get(`/api/sales-documents/${id}/download`, {
    responseType: 'blob',
  });
  return response.data;
};

export const deleteSalesDocument = async (id: number) => {
  const response = await api.delete(`/api/sales-documents/${id}`);
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

export const sendQuoteEmail = async (
  quoteId: number,
  emailData: {
    template_id: number;
    to_email: string;
    cc?: string;
    bcc?: string;
    custom_message?: string;
    include_available_extras?: boolean;
    include_specification_sheet?: boolean;
  },
  attachments?: File[]
) => {
  const formData = new FormData();
  formData.append('email_data', JSON.stringify(emailData));
  if (attachments?.length) {
    for (const file of attachments) {
      formData.append('attachments', file);
    }
  }
  const response = await api.post(`/api/quotes/${quoteId}/send-email`, formData, {
    timeout: EMAIL_AND_UPLOAD_TIMEOUT_MS,
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
  return response.data;
};

/** Public quote view by token (no auth). Used when customer opens "View your quote" link. */
export const getPublicQuoteView = async (viewToken: string) => {
  const response = await api.get(`/api/public/quotes/view/${viewToken}`);
  return response.data;
};

/** Public configurator (no auth). */
export const publicConfiguratorStart = async (campaignSlug?: string) => {
  const response = await api.post(
    '/api/public/configurator/start',
    { campaign_slug: campaignSlug ?? 'configure' },
    { skipAuthRedirect: true }
  );
  return response.data as { access_token: string; configure_url: string; status: string };
};

export const getPublicConfiguratorContext = async (token: string) => {
  const response = await api.get(`/api/public/configurator/${token}`, { skipAuthRedirect: true });
  return response.data as PublicConfiguratorContext;
};

export const publicConfiguratorRegister = async (
  token: string,
  body: { name: string; email?: string; phone?: string; postcode?: string }
) => {
  const response = await api.post(`/api/public/configurator/${token}/register`, body, {
    skipAuthRedirect: true,
  });
  return response.data as PublicConfiguratorContext;
};

export const getPublicConfiguratorCatalog = async () => {
  const response = await api.get('/api/public/configurator/catalog', { skipAuthRedirect: true });
  return response.data as ConfiguratorCatalogResponse;
};

export const previewPublicConfiguratorConfiguration = async (
  token: string,
  configuration: QuoteConfigurationPayload,
  customerPostcode?: string
) => {
  const response = await api.post(
    `/api/public/configurator/${token}/preview`,
    { configuration, customer_postcode: customerPostcode?.trim() || undefined },
    { skipAuthRedirect: true }
  );
  return response.data as ConfiguratorPreviewResponse;
};

export const savePublicConfiguratorConfiguration = async (
  token: string,
  configuration: QuoteConfigurationPayload
) => {
  const response = await api.put(`/api/public/configurator/${token}/configuration`, configuration, {
    skipAuthRedirect: true,
  });
  return response.data as PublicConfiguratorContext;
};

export const submitPublicConfiguratorLayout = async (token: string) => {
  const response = await api.post(`/api/public/configurator/${token}/submit`, null, {
    skipAuthRedirect: true,
  });
  return response.data as PublicConfiguratorContext;
};

export const createConfiguratorInvite = async (body: {
  customer_id?: number;
  lead_id?: number;
  campaign_slug?: string;
}) => {
  const response = await api.post('/api/configurator-invites', body);
  return response.data as ConfiguratorInvite;
};

export const listConfiguratorInvites = async (params?: {
  status?: string;
  assigned_to_me?: boolean;
  unread_only?: boolean;
  limit?: number;
}) => {
  const response = await api.get('/api/configurator-invites', { params });
  return response.data as { items: ConfiguratorInvite[]; total: number };
};

export const getUnreadConfiguratorSubmissionsCount = async (): Promise<{ count: number }> => {
  const response = await api.get('/api/configurator-invites/unread-count');
  return response.data as { count: number };
};

export const markConfiguratorInviteViewed = async (inviteId: number): Promise<ConfiguratorInvite> => {
  const response = await api.post(`/api/configurator-invites/${inviteId}/mark-viewed`);
  dispatchRefreshConfiguratorSubmissions();
  return response.data as ConfiguratorInvite;
};

/** Dispatched after a submission is opened so the header badge updates. */
export const LEADLOCK_REFRESH_CONFIGURATOR_SUBMISSIONS_EVENT =
  'leadlock:refreshConfiguratorSubmissions';

export function dispatchRefreshConfiguratorSubmissions(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(LEADLOCK_REFRESH_CONFIGURATOR_SUBMISSIONS_EVENT));
  }
}

/** Company logo URL for header and login page (no auth required). */
export const getPublicCompanyLogo = async (): Promise<{ logo_url: string | null }> => {
  const response = await api.get('/api/public/company-logo');
  return response.data;
};

/** Base URL for API (same as axios uses for authenticated calls). */
export const getApiBaseUrl = () => resolveApiBaseUrl();

export const getDataSummary = async (): Promise<{
  customers: number;
  leads: number;
  leads_not_archived: number;
  users: number;
  database_host?: string | null;
  use_public_database_url?: boolean;
}> => {
  const response = await api.get('/api/auth/data-summary');
  return response.data;
};

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

/** Get latest customer view URL for a quote (mints a share link if none exists yet). */
export const getQuoteViewLink = async (quoteId: number): Promise<{ view_url: string | null }> => {
  const response = await api.get(`/api/quotes/${quoteId}/view-link`);
  return response.data;
};

/** Ensure a customer view token exists and return the URL (no email or SMS). */
export const postQuoteShareLink = async (
  quoteId: number,
  body?: { include_available_extras?: boolean; include_specification_sheet?: boolean }
): Promise<{ view_url: string; quote_email_id: number }> => {
  const response = await api.post(`/api/quotes/${quoteId}/share-link`, body ?? {});
  return response.data;
};

/** Send the customer view link by SMS (Twilio). */
export const sendQuoteSms = async (
  quoteId: number,
  data?: { to_phone?: string; body?: string; include_available_extras?: boolean; include_specification_sheet?: boolean }
): Promise<{ view_url: string; quote_email_id: number; message: string }> => {
  const response = await api.post(`/api/quotes/${quoteId}/send-sms`, data ?? {});
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

// Quote Template API functions
export const getQuoteTemplates = async () => {
  const response = await api.get('/api/quote-templates');
  return response.data;
};

export const getQuoteTemplate = async (templateId: number) => {
  const response = await api.get(`/api/quote-templates/${templateId}`);
  return response.data;
};

export const createQuoteTemplate = async (templateData: {
  name: string;
  description?: string;
  email_subject_template: string;
  email_body_template: string;
  is_default?: boolean;
  sales_document_ids?: number[];
}) => {
  const response = await api.post('/api/quote-templates', templateData);
  return response.data;
};

export const updateQuoteTemplate = async (templateId: number, templateData: {
  name?: string;
  description?: string;
  email_subject_template?: string;
  email_body_template?: string;
  is_default?: boolean;
  sales_document_ids?: number[];
}) => {
  const response = await api.put(`/api/quote-templates/${templateId}`, templateData);
  return response.data;
};

export const deleteQuoteTemplate = async (templateId: number) => {
  const response = await api.delete(`/api/quote-templates/${templateId}`);
  return response.data;
};

export const previewQuoteTemplate = async (templateId: number, previewData?: {
  quote_id?: number;
}) => {
  const response = await api.post(`/api/quote-templates/${templateId}/preview`, previewData || {});
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

export const revealCompanyBankDetails = async (): Promise<{
  account_number?: string | null;
  sort_code?: string | null;
}> => {
  const response = await api.get('/api/settings/company/bank-details');
  return response.data;
};

export const listFacebookAdverts = async (): Promise<FacebookAdvertProfile[]> => {
  const response = await api.get('/api/settings/facebook-adverts');
  return response.data;
};

export const createFacebookAdvert = async (payload: {
  name: string;
  offer_type?: string;
  image_url?: string;
  is_active?: boolean;
}): Promise<FacebookAdvertProfile> => {
  const response = await api.post('/api/settings/facebook-adverts', payload);
  return response.data;
};

export const updateFacebookAdvert = async (
  advertId: number,
  payload: {
    name?: string;
    offer_type?: string;
    image_url?: string;
    is_active?: boolean;
  }
): Promise<FacebookAdvertProfile> => {
  const response = await api.patch(`/api/settings/facebook-adverts/${advertId}`, payload);
  return response.data;
};

// Delivery & installation estimate (mileage, travel time, overnight, cost breakdown)
export const estimateDeliveryInstall = async (
  customerPostcode: string,
  installationHours: number,
  options?: { numberOfBoxes?: number; deliveryOnly?: boolean }
) => {
  const response = await api.post('/api/delivery-install/estimate', {
    customer_postcode: customerPostcode,
    installation_hours: installationHours,
    number_of_boxes: options?.numberOfBoxes,
    delivery_only: options?.deliveryOnly ?? false,
  });
  return response.data;
};

// Quote API functions
export const createQuote = async (quoteData: {
  customer_id: number;
  lead_id: number;  // Required: quotes must be linked to an enquiry (lead)
  quote_number?: string;
  version?: number;
  valid_until?: string;
  terms_and_conditions?: string;
  specification_sheet?: string;
  notes?: string;
  deposit_amount?: number;
  /** When true, lead stays QUALIFIED until applyQualifiedToQuotedTransition is called */
  defer_qualified_to_quoted_transition?: boolean;
  items: Array<{
    product_id?: number;
    description: string;
    quantity: number;
    unit_price: number;
    is_custom?: boolean;
    sort_order?: number;
    parent_index?: number;
    line_type?: 'DELIVERY' | 'INSTALLATION';
    include_in_building_discount?: boolean;
  }>;
  discount_template_ids?: number[];
  temperature?: QuoteTemperature;
  include_spec_sheets?: boolean;
  include_specification_sheet?: boolean;
  include_available_optional_extras?: boolean;
  include_delivery_installation_contact_note?: boolean;
  fulfillment_method?: QuoteFulfillmentMethod;
  use_alternate_delivery_address?: boolean;
  delivery_address_line1?: string;
  delivery_address_line2?: string;
  delivery_city?: string;
  delivery_county?: string;
  delivery_postcode?: string;
  delivery_country?: string;
  delivery_location_notes?: string;
}) => {
  const response = await api.post('/api/quotes', quoteData);
  return response.data;
};

/** Run deferred QUALIFIED→QUOTED after finalizing a bootstrapped draft */
export const applyQualifiedToQuotedTransition = async (quoteId: number) => {
  await api.post(`/api/quotes/${quoteId}/apply-qualified-to-quoted`);
};

/** Clone a non-draft quote into a new DRAFT (new id / quote_number). */
export const duplicateQuoteToDraft = async (quoteId: number) => {
  const response = await api.post(`/api/quotes/${quoteId}/duplicate-to-draft`);
  return response.data;
};

export const getQuotes = async (options?: {
  status?: QuoteStatus;
  lifecycle?: 'live' | 'closed';
  search?: string;
  temperature?: QuoteTemperature;
  page?: number;
  page_size?: number;
  includeArchived?: boolean;
}) => {
  const params: Record<string, string | number | boolean> = {};
  if (options?.status) params.status = options.status;
  if (options?.lifecycle) params.lifecycle = options.lifecycle;
  if (options?.search?.trim()) params.search = options.search.trim();
  if (options?.temperature) params.temperature = options.temperature;
  if (options?.page != null) params.page = options.page;
  if (options?.page_size != null) params.page_size = options.page_size;
  if (options?.includeArchived) params.includeArchived = true;
  const response = await api.get('/api/quotes', { params: Object.keys(params).length ? params : undefined });
  return response.data as QuoteListPayload;
};

export const getQuote = async (quoteId: number) => {
  const response = await api.get(`/api/quotes/${quoteId}`);
  return response.data;
};

export const getDealerWelcome = async (): Promise<DealerWelcome> => {
  const response = await api.get('/api/dealer-portal/welcome');
  return response.data;
};

export const getDealerProducts = async () => {
  const response = await api.get('/api/dealer-portal/products');
  return response.data;
};

export const getDealerProfile = async (): Promise<DealerProfile> => {
  const response = await api.get('/api/dealer-portal/profile');
  return response.data;
};

export const getDealerDiscountPolicy = async (): Promise<DealerAllowedDiscountPolicy> => {
  const response = await api.get('/api/dealer-portal/discount-policy');
  return response.data;
};

export const getDealersForSettings = async (): Promise<DealerSummary[]> => {
  const response = await api.get('/api/settings/dealers');
  return response.data;
};

export const getDealerDiscountPolicyForAdmin = async (
  dealerId: number
): Promise<DealerDiscountPolicyAdminResponse> => {
  const response = await api.get(`/api/settings/dealers/${dealerId}/discount-policy`);
  return response.data;
};

export const updateDealerDiscountPolicyForAdmin = async (
  dealerId: number,
  payload: DealerDiscountPolicyAdminPayload
): Promise<DealerDiscountPolicyAdminResponse> => {
  const response = await api.put(`/api/settings/dealers/${dealerId}/discount-policy`, payload);
  return response.data;
};

export const updateDealerProfile = async (
  payload: DealerProfileUpdatePayload
): Promise<DealerProfile> => {
  const response = await api.put('/api/dealer-portal/profile', payload);
  return response.data;
};

export const uploadDealerLogo = async (file: File): Promise<DealerProfile> => {
  const formData = new FormData();
  formData.append('logo', file);
  const response = await api.post('/api/dealer-portal/profile/logo', formData, {
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
  return response.data;
};

export const getDealerQuotes = async (): Promise<QuoteListPayload> => {
  const response = await api.get('/api/dealer-portal/quotes');
  return response.data;
};

export const createDealerQuote = async (payload: DealerQuoteCreatePayload) => {
  const response = await api.post('/api/dealer-portal/quotes', payload);
  return response.data;
};

export const getDealerQuote = async (quoteId: number) => {
  const response = await api.get(`/api/dealer-portal/quotes/${quoteId}`);
  return response.data;
};

export const downloadDealerQuotePdf = async (quoteId: number) => {
  const response = await api.get(`/api/dealer-portal/quotes/${quoteId}/pdf`, {
    responseType: 'blob',
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const disposition = response.headers['content-disposition'];
  let filename = 'DealerQuote.pdf';
  if (disposition) {
    const match = /filename="?([^";\n]+)"?/.exec(disposition);
    if (match) filename = match[1].trim();
  }
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => window.URL.revokeObjectURL(url), 100);
};

export const patchQuote = async (quoteId: number, data: Record<string, unknown>) => {
  const response = await api.patch(`/api/quotes/${quoteId}`, data, {
    timeout: EMAIL_AND_UPLOAD_TIMEOUT_MS,
  });
  return response.data;
};

export const acceptQuote = async (quoteId: number) => {
  const response = await api.patch(`/api/quotes/${quoteId}`, { status: 'ACCEPTED' }, {
    timeout: EMAIL_AND_UPLOAD_TIMEOUT_MS,
  });
  return response.data;
};

export const ensureQuoteOrder = async (quoteId: number) => {
  const response = await api.post(`/api/quotes/${quoteId}/ensure-order`);
  return response.data;
};

export const cancelDraftQuote = async (quoteId: number) => {
  await api.delete(`/api/quotes/${quoteId}`);
};

export const getOrders = async () => {
  const response = await api.get('/api/orders');
  return response.data;
};

export const getCustomerOrders = async (customerId: number) => {
  const response = await api.get(`/api/customers/${customerId}/orders`);
  return response.data;
};

export const createLeadFromCustomer = async (
  customerId: number,
  data?: { description?: string; product_interest?: string; lead_type?: string; lead_source?: string; scope_notes?: string }
) => {
  const response = await api.post(`/api/customers/${customerId}/leads`, data ?? {});
  return response.data;
};

export const deleteCustomer = async (customerId: number) => {
  await api.delete(`/api/customers/${customerId}`);
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
    notes?: string | null;
    /** One-way drive time in hours; production send uses 2× for round-trip */
    travel_time_hours_one_way?: number | null;
    use_alternate_delivery_address?: boolean;
    delivery_address_line1?: string | null;
    delivery_address_line2?: string | null;
    delivery_city?: string | null;
    delivery_county?: string | null;
    delivery_postcode?: string | null;
    delivery_country?: string | null;
    delivery_location_notes?: string | null;
  }
) => {
  const response = await api.patch(`/api/orders/${orderId}`, data);
  return response.data;
};

export const deleteOrder = async (orderId: number) => {
  await api.delete(`/api/orders/${orderId}`);
};

/** Fetches deposit invoice PDF as Blob for download or attach-to-email. */
export const fetchOrderDepositInvoiceBlob = async (orderId: number): Promise<Blob> => {
  const response = await api.get(`/api/orders/${orderId}/invoice/deposit-pdf`, {
    responseType: 'blob',
  });
  return new Blob([response.data], { type: 'application/pdf' });
};

/** Fetches paid-in-full invoice PDF as Blob for download or attach-to-email. */
export const fetchOrderPaidInFullInvoiceBlob = async (orderId: number): Promise<Blob> => {
  const response = await api.get(`/api/orders/${orderId}/invoice/paid-in-full-pdf`, {
    responseType: 'blob',
  });
  return new Blob([response.data], { type: 'application/pdf' });
};

export const getOrderDepositInvoicePdf = async (orderId: number) => {
  const blob = await fetchOrderDepositInvoiceBlob(orderId);
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Invoice_Deposit_${orderId}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const getOrderPaidInFullInvoicePdf = async (orderId: number) => {
  const blob = await fetchOrderPaidInFullInvoiceBlob(orderId);
  const url = window.URL.createObjectURL(blob);
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

export const sendOrderReviewRequest = async (
  orderId: number,
  data?: { channel: 'email' | 'sms'; use_returning_template?: boolean | null }
) => {
  const response = await api.post(`/api/orders/${orderId}/send-review-request`, data ?? { channel: 'sms' });
  return response.data as {
    success: boolean;
    channel?: string | null;
    staff_reminder_acted?: boolean;
    message?: string | null;
  };
};

export const sendOrderPaymentLink = async (
  orderId: number,
  data: {
    channel: 'email' | 'sms';
    payment_url?: string;
    to_email?: string;
    to_phone?: string;
    subject?: string;
    body?: string;
    template_id?: number;
    save_link_on_order?: boolean;
  }
) => {
  const response = await api.post(`/api/orders/${orderId}/send-payment-link`, data);
  return response.data as { message: string; channel: string };
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

type _CustomerFile = import('@/lib/types').CustomerFile;
type _CustomerFileKind = import('@/lib/types').CustomerFileKind;

/** List customer-level files (no quote/order context). Auth required. */
export const listCustomerFiles = async (
  customerId: number
): Promise<_CustomerFile[]> => {
  const response = await api.get(`/api/customers/${customerId}/files`);
  return response.data;
};

/** Upload a customer-level file (no quote/order context). Auth required. */
export const uploadCustomerFile = async (
  customerId: number,
  file: File,
  kind?: _CustomerFileKind
): Promise<_CustomerFile> => {
  const formData = new FormData();
  formData.append('file', file);
  if (kind) formData.append('kind', kind);
  const response = await api.post(`/api/customers/${customerId}/files`, formData, {
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
  return response.data;
};

/** List files attached to a quote. Auth required. */
export const listQuoteFiles = async (
  quoteId: number
): Promise<_CustomerFile[]> => {
  const response = await api.get(`/api/quotes/${quoteId}/files`);
  return response.data;
};

/** Upload a file to a quote (auto-attaches to the order on acceptance). */
export const uploadQuoteFile = async (
  quoteId: number,
  file: File,
  kind?: _CustomerFileKind
): Promise<_CustomerFile> => {
  const formData = new FormData();
  formData.append('file', file);
  if (kind) formData.append('kind', kind);
  const response = await api.post(`/api/quotes/${quoteId}/files`, formData, {
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
  return response.data;
};

/** List files attached to an order (includes files inherited from the quote). */
export const listOrderFiles = async (
  orderId: number
): Promise<_CustomerFile[]> => {
  const response = await api.get(`/api/orders/${orderId}/files`);
  return response.data;
};

/** Upload a file directly to an order (no quote link). */
export const uploadOrderFile = async (
  orderId: number,
  file: File,
  kind?: _CustomerFileKind
): Promise<_CustomerFile> => {
  const formData = new FormData();
  formData.append('file', file);
  if (kind) formData.append('kind', kind);
  const response = await api.post(`/api/orders/${orderId}/files`, formData, {
    transformRequest: [(data: unknown, headers?: Record<string, unknown>) => {
      if (data instanceof FormData && headers) delete (headers as Record<string, unknown>)['Content-Type'];
      return data;
    }],
  });
  return response.data;
};

/** Delete a customer/quote/order file (also removes from Cloudinary). */
export const deleteCustomerFile = async (fileId: number): Promise<void> => {
  await api.delete(`/api/customer-files/${fileId}`);
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

export const getReviewHubContext = async (token: string) => {
  const response = await api.get(`/api/public/review/${token}`, { skipAuthRedirect: true });
  return response.data;
};

export const getReviewPrizeContext = async (token: string) => {
  const response = await api.get(`/api/public/review-prize/${token}`, { skipAuthRedirect: true });
  return response.data;
};

export const submitReviewPrizeEntry = async (token: string, platforms: string[]) => {
  const response = await api.post(
    `/api/public/review-prize/${token}`,
    { platforms },
    { skipAuthRedirect: true }
  );
  return response.data;
};

export const getReviewPrizeDrawEntries = async (params?: { month?: string; status?: string }) => {
  const response = await api.get('/api/review-prize-draw/entries', { params });
  return response.data as { entries: import('@/lib/types').ReviewPrizeDrawEntryListItem[]; approved_count: number };
};

export const approveReviewPrizeDrawEntry = async (entryId: number) => {
  const response = await api.post(`/api/review-prize-draw/entries/${entryId}/approve`);
  return response.data;
};

export const rejectReviewPrizeDrawEntry = async (entryId: number, note?: string) => {
  const response = await api.post(`/api/review-prize-draw/entries/${entryId}/reject`, { note: note || null });
  return response.data;
};

export const getReviewPrizeDrawWinner = async (month: string) => {
  const response = await api.get('/api/review-prize-draw/winners', { params: { month } });
  return response.data as import('@/lib/types').ReviewPrizeDrawWinner | null;
};

export const pickReviewPrizeDrawWinner = async (month: string) => {
  const response = await api.post('/api/review-prize-draw/pick-winner', { month });
  return response.data as import('@/lib/types').ReviewPrizeDrawWinner;
};

export const resetReviewPrizeDrawWinner = async (month: string) => {
  const response = await api.post('/api/review-prize-draw/reset-winner', { month });
  return response.data as { success: boolean; month: string };
};

export const sendReviewPrizeDrawCongratulations = async (
  month: string,
  data: { channel: 'email' | 'sms'; force?: boolean }
) => {
  const response = await api.post('/api/review-prize-draw/send-congratulations', {
    month,
    channel: data.channel,
    force: data.force ?? false,
  });
  return response.data as import('@/lib/types').ReviewPrizeDrawWinner;
};

export const updateDraftQuote = async (quoteId: number, quoteData: {
  valid_until?: string;
  terms_and_conditions?: string;
  specification_sheet?: string;
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
    include_in_building_discount?: boolean;
  }>;
  discount_template_ids?: number[];
  temperature?: QuoteTemperature;
  include_spec_sheets?: boolean;
  include_specification_sheet?: boolean;
  include_available_optional_extras?: boolean;
  include_delivery_installation_contact_note?: boolean;
  fulfillment_method?: QuoteFulfillmentMethod;
  use_alternate_delivery_address?: boolean;
  delivery_address_line1?: string;
  delivery_address_line2?: string;
  delivery_city?: string;
  delivery_county?: string;
  delivery_postcode?: string;
  delivery_country?: string;
  delivery_location_notes?: string;
}) => {
  const response = await api.put(`/api/quotes/${quoteId}/draft`, quoteData, {
    timeout: EMAIL_AND_UPLOAD_TIMEOUT_MS,
  });
  return response.data;
};

export const getCustomerQuotes = async (customerId: number) => {
  const response = await api.get(`/api/quotes/customers/${customerId}`);
  return response.data;
};

export const getLeadQuotes = async (leadId: number) => {
  const response = await api.get(`/api/leads/${leadId}/quotes`);
  return response.data;
};

export const downloadLeadHandoverPdf = async (leadId: number, options?: LeadHandoverPdfOptions) => {
  const response = await api.get(`/api/leads/${leadId}/handover-pdf`, {
    responseType: 'blob',
    params: { days: options?.days ?? 14 },
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const disposition = response.headers['content-disposition'];
  let filename = `Lead_Handover_${leadId}.pdf`;
  if (disposition) {
    const match = /filename="?([^";\n]+)"?/.exec(disposition);
    if (match) filename = match[1].trim();
  }
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => window.URL.revokeObjectURL(url), 100);
};

export const previewQuotePdf = async (
  quoteId: number,
  options?: { includeSpecSheets?: boolean; includeOptionalExtras?: boolean; includeSpecificationSheet?: boolean }
) => {
  const params: Record<string, string> = {};
  if (options?.includeSpecSheets === false) params.include_spec_sheets = 'false';
  if (options?.includeOptionalExtras === false) params.include_optional_extras = 'false';
  if (options?.includeOptionalExtras === true) params.include_optional_extras = 'true';
  if (options?.includeSpecificationSheet === true) params.include_specification_sheet = 'true';
  if (options?.includeSpecificationSheet === false) params.include_specification_sheet = 'false';
  const response = await api.get(`/api/quotes/${quoteId}/preview-pdf`, {
    responseType: 'blob',
    params,
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const disposition = response.headers['content-disposition'];
  let filename = 'Quote.pdf';
  if (disposition) {
    const match = /filename="?([^";\n]+)"?/.exec(disposition);
    if (match) filename = match[1].trim();
  }
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
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
  allow_trade_dealer_sale?: boolean;
  base_price: number;
  unit?: string;
  sku?: string;
  image_url?: string;
  specifications?: string;
  size?: string;
  height?: string;
  floor_plan_url?: string;
  width?: number;
  length?: number;
  configurator_width?: number;
  configurator_length?: number;
  configurator_front_face?: 'top' | 'right' | 'bottom' | 'left' | null;
  configurator_connection_profile?: 'corner_left' | 'corner_right' | null;
  configurator_is_corner_box?: boolean;
  configurator_is_starter_box?: boolean;
  allow_in_configurator?: boolean;
  configurator_per_box?: boolean;
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
  allow_trade_dealer_sale?: boolean;
  base_price?: number;
  unit?: string;
  sku?: string;
  /** Use `null` to clear; `undefined` omits the field from the PATCH body. */
  image_url?: string | null;
  specifications?: string;
  size?: string;
  height?: string;
  floor_plan_url?: string | null;
  width?: number;
  length?: number;
  configurator_width?: number | null;
  configurator_length?: number | null;
  configurator_front_face?: 'top' | 'right' | 'bottom' | 'left' | null;
  configurator_connection_profile?: 'corner_left' | 'corner_right' | null;
  configurator_is_corner_box?: boolean;
  configurator_is_starter_box?: boolean;
  allow_in_configurator?: boolean;
  configurator_per_box?: boolean;
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
  done?: boolean;
  priority?: string;
  reminder_type?: string;
  assigned_to_me?: boolean;
}) => {
  const response = await api.get('/api/reminders', { params });
  return response.data;
};

export const createUserTask = async (data: {
  title: string;
  message: string;
  due_date: string;
  assigned_to_id?: number;
  customer_id?: number;
}) => {
  const response = await api.post('/api/reminders/tasks', data);
  return response.data;
};

export const getAssignableUsers = async () => {
  const response = await api.get('/api/users/assignable');
  return response.data;
};

export const getAuthMe = async () => {
  const response = await api.get('/api/auth/me');
  return response.data as AuthMe;
};

export const getConfiguratorAccessStatus = async () => {
  const response = await api.get('/api/configurator/access');
  return response.data as ConfiguratorAccessStatus;
};

export const getConfiguratorCatalog = async () => {
  const response = await api.get('/api/configurator/catalog');
  return response.data as ConfiguratorCatalogResponse;
};

export const previewConfiguratorConfiguration = async (
  configuration: QuoteConfigurationPayload,
  options?: { customerPostcode?: string }
) => {
  const response = await api.post('/api/configurator/preview', {
    configuration,
    customer_postcode: options?.customerPostcode?.trim() || undefined,
  });
  return response.data as ConfiguratorPreviewResponse;
};

export const getQuoteConfiguration = async (quoteId: number) => {
  const response = await api.get(`/api/quotes/${quoteId}/configuration`);
  return response.data as QuoteConfigurationResponse;
};

export const saveQuoteConfiguration = async (quoteId: number, payload: QuoteConfigurationPayload) => {
  const response = await api.put(`/api/quotes/${quoteId}/configuration`, payload);
  return response.data as QuoteConfigurationResponse;
};

export const applyQuoteConfiguration = async (quoteId: number) => {
  const response = await api.post(`/api/quotes/${quoteId}/configuration/apply`);
  return response.data;
};

export const getLoginQuote = async (): Promise<{ quote: string; source: 'ai' | 'fallback' | string }> => {
  const response = await api.get('/api/auth/login-quote');
  return response.data;
};

let staleSummaryInFlight: Promise<StaleSummary> | null = null;
let staleSummaryCache: { data: StaleSummary; expiresAt: number } | null = null;
const STALE_SUMMARY_TTL_MS = 12_000;

/** Dispatched after reminder mutations so the header badge updates without a route change. */
export const LEADLOCK_REFRESH_REMINDERS_EVENT = 'leadlock:refreshReminderCounts';

export function dispatchRefreshReminderCounts(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(LEADLOCK_REFRESH_REMINDERS_EVENT));
  }
}

/** Clear client cache after mutations so header counts refresh immediately. */
export const invalidateStaleSummaryCache = () => {
  staleSummaryCache = null;
  staleSummaryInFlight = null;
  dispatchRefreshReminderCounts();
};

export const getStaleSummary = async (): Promise<StaleSummary> => {
  const now = Date.now();
  if (staleSummaryCache && now < staleSummaryCache.expiresAt) {
    return staleSummaryCache.data;
  }
  if (staleSummaryInFlight) {
    return staleSummaryInFlight;
  }
  staleSummaryInFlight = (async () => {
    try {
      const response = await api.get('/api/reminders/stale-summary');
      const data = response.data as StaleSummary;
      staleSummaryCache = { data, expiresAt: Date.now() + STALE_SUMMARY_TTL_MS };
      return data;
    } finally {
      staleSummaryInFlight = null;
    }
  })();
  return staleSummaryInFlight;
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

export const cleanupAutomatedReminders = async (params?: {
  priority?: string;
  reminder_type?: string;
  assigned_to_me?: boolean;
}): Promise<AutomatedReminderCleanupResult> => {
  const response = await api.post('/api/reminders/cleanup-automated', params ?? {});
  return response.data;
};

export const generateWeeklyPlan = async (params?: {
  auto_execute?: boolean;
  dry_run?: boolean;
}): Promise<WeeklyPlanRun> => {
  const response = await api.post('/api/reminders/weekly-plan/generate', null, {
    params: {
      auto_execute: params?.auto_execute ?? false,
      dry_run: params?.dry_run ?? false,
    },
    timeout: 120_000,
  });
  return response.data;
};

export const getLatestWeeklyPlan = async (): Promise<WeeklyPlanListResponse> => {
  const response = await api.get('/api/reminders/weekly-plan/latest');
  return response.data;
};

export const executeWeeklyPlanAuto = async (runId: number): Promise<{ sent_count: number; message: string }> => {
  const response = await api.post(`/api/reminders/weekly-plan/${runId}/execute-auto`, null, {
    timeout: 120_000,
  });
  return response.data;
};

export const sendWeeklyPlanItem = async (itemId: number): Promise<WeeklyPlanItem> => {
  const response = await api.post(`/api/reminders/weekly-plan/items/${itemId}/send`, null, {
    timeout: 120_000,
  });
  return response.data;
};

export const sendWeeklyPlanItemsBulk = async (itemIds: number[]): Promise<WeeklyPlanBulkSendResult> => {
  const response = await api.post('/api/reminders/weekly-plan/items/send-bulk', { item_ids: itemIds }, {
    timeout: 120_000,
  });
  return response.data;
};

export const updateWeeklyPlanItem = async (
  itemId: number,
  payload: {
    status?: WeeklyPlanItemStatus;
    outcome_result?: string;
    response_received?: boolean;
    suggested_message?: string;
  }
): Promise<WeeklyPlanItem> => {
  const response = await api.patch(`/api/reminders/weekly-plan/items/${itemId}`, payload);
  return response.data;
};

export const getWeeklyPlanMetrics = async (runId: number): Promise<Record<string, unknown>> => {
  const response = await api.get(`/api/reminders/weekly-plan/${runId}/metrics`);
  return response.data;
};

export const getWeeklyPlanTrend = async (weeks = 8): Promise<{
  items: Array<{
    run_id: number;
    week_start: string;
    average_order_likelihood: number;
    total_items: number;
  }>;
}> => {
  const response = await api.get('/api/reminders/weekly-plan/trend', { params: { weeks } });
  return response.data;
};

export const getWeeklyPlanTemplates = async (): Promise<WeeklyPlanTemplate[]> => {
  const response = await api.get('/api/reminders/weekly-plan/templates');
  return response.data;
};

export const createWeeklyPlanTemplate = async (payload: WeeklyPlanTemplateCreate): Promise<WeeklyPlanTemplate> => {
  const response = await api.post('/api/reminders/weekly-plan/templates', payload);
  return response.data;
};

export const updateWeeklyPlanTemplate = async (
  templateId: number,
  payload: WeeklyPlanTemplateUpdate
): Promise<WeeklyPlanTemplate> => {
  const response = await api.put(`/api/reminders/weekly-plan/templates/${templateId}`, payload);
  return response.data;
};

export const deleteWeeklyPlanTemplate = async (templateId: number): Promise<{ message: string }> => {
  const response = await api.delete(`/api/reminders/weekly-plan/templates/${templateId}`);
  return response.data;
};

export const previewWeeklyPlanTemplate = async (
  templateId: number,
  payload?: { customer_name?: string; quote_number?: string }
): Promise<WeeklyPlanTemplatePreviewResponse> => {
  const response = await api.post(`/api/reminders/weekly-plan/templates/${templateId}/preview`, payload || {});
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
  notes?: string,
  activityType: ActivityType = ActivityType.CALL_ATTEMPTED
): Promise<void> => {
  await api.post(`/api/customers/${customerId}/activities`, {
    activity_type: activityType,
    notes: notes || undefined,
  });
};

/** Log a manual note on the customer activity timeline. */
export const logCustomerNote = async (
  customerId: number,
  notes: string
): Promise<void> => {
  await api.post(`/api/customers/${customerId}/activities`, {
    activity_type: ActivityType.NOTE,
    notes: notes.trim(),
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

export const getReminderRules = async () => {
  const response = await api.get('/api/reminders/rules');
  return response.data;
};

export const updateReminderRule = async (
  ruleId: number,
  data: {
    threshold_minutes?: number;
    is_active?: boolean;
    priority?: string;
    suggested_action?: string;
    customer_outreach_channel?: string | null;
    customer_outreach_sms_template_id?: number | null;
    customer_outreach_email_template_id?: number | null;
    customer_outreach_cooldown_days?: number | null;
  }
) => {
  const response = await api.put(`/api/reminders/rules/${ruleId}`, data);
  return response.data;
};

export const createReminderRule = async (data: {
  rule_name: string;
  entity_type: string;
  status?: string | null;
  threshold_minutes: number;
  check_type: string;
  is_active: boolean;
  priority: string;
  suggested_action: string;
  customer_outreach_channel?: string | null;
  customer_outreach_sms_template_id?: number | null;
  customer_outreach_email_template_id?: number | null;
  customer_outreach_cooldown_days?: number | null;
}) => {
  const response = await api.post('/api/reminders/rules', data);
  return response.data;
};

export const deleteReminderRule = async (ruleId: number) => {
  const response = await api.delete(`/api/reminders/rules/${ruleId}`);
  return response.data;
};

export const getOutreachSends = async (params?: {
  channel?: 'SMS' | 'EMAIL';
  target_type?: OutreachSendTargetType;
  customer_id?: number;
  page?: number;
  page_size?: number;
}): Promise<OutreachSendListResponse> => {
  const response = await api.get('/api/reminders/outreach-sends', { params });
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
  max_uses?: number | null;
  expires_at?: string | null;
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
  max_uses?: number | null;
  expires_at?: string | null;
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

export const deleteDiscountRequest = async (requestId: number) => {
  await api.delete(`/api/discount-requests/${requestId}`);
};

// Customer import/export (Company Settings)
export const downloadCustomerImportExample = async () => {
  const response = await api.get('/api/settings/customers/import-example', {
    responseType: 'blob',
  });
  const blob = new Blob([response.data], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', 'customer-import-example.csv');
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const importCustomersFromCsv = async (file: File): Promise<{
  created: number;
  skipped: number;
  errors: Array<{ row: number; message: string }>;
}> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/api/settings/customers/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

// Users API (DIRECTOR only)
export const listUsers = async () => {
  const response = await api.get('/api/users');
  return response.data;
};

export const createUser = async (data: {
  email: string;
  full_name: string;
  password: string;
  role: string;
  dealer_id?: number;
  dealer_commission_pct?: number;
}) => {
  const response = await api.post('/api/users', data);
  return response.data;
};

export const updateUser = async (
  userId: number,
  data: {
    full_name?: string;
    role?: string;
    password?: string;
    dealer_id?: number;
    dealer_commission_pct?: number;
  }
) => {
  const response = await api.put(`/api/users/${userId}`, data);
  return response.data;
};

export const deactivateUser = async (userId: number) => {
  const response = await api.delete(`/api/users/${userId}`);
  return response.data;
};

export const downloadCustomerExport = async () => {
  const response = await api.get('/api/settings/customers/export', {
    responseType: 'blob',
  });
  const dateStr = new Date().toISOString().slice(0, 10);
  const blob = new Blob([response.data], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `customers-export-${dateStr}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

// Sales Reports API functions
export const getPipelineValueReport = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/pipeline-value', { params });
  return response.data;
};

export const downloadPipelineValueReportPdf = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/pipeline-value/pdf', {
    responseType: 'blob',
    params,
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Pipeline_Value_Report_${new Date().toISOString().slice(0, 10)}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const getSourcePerformanceReport = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/source-performance', { params });
  return response.data;
};

export const downloadSourcePerformanceReportPdf = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/source-performance/pdf', {
    responseType: 'blob',
    params,
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Source_Performance_Report_${new Date().toISOString().slice(0, 10)}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const getFacebookLeadConversionReport = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/facebook-lead-conversion', { params });
  return response.data;
};

export const downloadFacebookLeadConversionReportPdf = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/facebook-lead-conversion/pdf', {
    responseType: 'blob',
    params,
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Facebook_Lead_To_Order_Report_${new Date().toISOString().slice(0, 10)}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const downloadFacebookLeadConversionReportCsv = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/facebook-lead-conversion.csv', {
    responseType: 'blob',
    params,
  });
  const blob = new Blob([response.data], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Facebook_Lead_To_Order_Report_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const getCloserPerformanceReport = async () => {
  const response = await api.get('/api/reports/closer-performance');
  return response.data;
};

export const downloadCloserPerformanceReportPdf = async () => {
  const response = await api.get('/api/reports/closer-performance/pdf', {
    responseType: 'blob',
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Closer_Performance_Report_${new Date().toISOString().slice(0, 10)}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const getQuoteEngagementReport = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/quote-engagement', { params });
  return response.data;
};

export const downloadQuoteEngagementReportPdf = async (filter?: DateRangeQueryParams) => {
  const params = buildDateRangeParams(filter);
  const response = await api.get('/api/reports/quote-engagement/pdf', {
    responseType: 'blob',
    params,
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Quote_Engagement_Report_${new Date().toISOString().slice(0, 10)}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const getWeeklySummaryReport = async () => {
  const response = await api.get('/api/reports/weekly-summary');
  return response.data;
};

export const downloadWeeklySummaryReportPdf = async () => {
  const response = await api.get('/api/reports/weekly-summary/pdf', {
    responseType: 'blob',
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `Weekly_Pipeline_Summary_${new Date().toISOString().slice(0, 10)}.pdf`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};
