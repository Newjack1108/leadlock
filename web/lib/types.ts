export enum LeadStatus {
  NEW = "NEW",
  CONTACT_ATTEMPTED = "CONTACT_ATTEMPTED",
  ENGAGED = "ENGAGED",
  QUALIFIED = "QUALIFIED",
  QUOTED = "QUOTED",
  WON = "WON",
  LOST = "LOST",
}

export enum ActivityType {
  SMS_SENT = "SMS_SENT",
  SMS_RECEIVED = "SMS_RECEIVED",
  EMAIL_SENT = "EMAIL_SENT",
  EMAIL_RECEIVED = "EMAIL_RECEIVED",
  CALL_ATTEMPTED = "CALL_ATTEMPTED",
  LIVE_CALL = "LIVE_CALL",
  WHATSAPP_SENT = "WHATSAPP_SENT",
  WHATSAPP_RECEIVED = "WHATSAPP_RECEIVED",
  NOTE = "NOTE",
}

export enum Timeframe {
  UNKNOWN = "UNKNOWN",
  IMMEDIATE = "IMMEDIATE",
  WITHIN_MONTH = "WITHIN_MONTH",
  WITHIN_QUARTER = "WITHIN_QUARTER",
  WITHIN_YEAR = "WITHIN_YEAR",
  EXPLORING = "EXPLORING",
}

export enum ProductCategory {
  STABLES = "STABLES",
  SHEDS = "SHEDS",
  CABINS = "CABINS",
}

export enum LeadType {
  UNKNOWN = "UNKNOWN",
  STABLES = "STABLES",
  SHEDS = "SHEDS",
  CABINS = "CABINS",
}

export enum LeadSource {
  UNKNOWN = "UNKNOWN",
  FACEBOOK = "FACEBOOK",
  INSTAGRAM = "INSTAGRAM",
  WEBSITE = "WEBSITE",
  MANUAL_ENTRY = "MANUAL_ENTRY",
  SMS = "SMS",
  EMAIL = "EMAIL",
  PHONE = "PHONE",
  REFERRAL = "REFERRAL",
  OTHER = "OTHER",
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
}

export interface UserEmailSettings {
  smtp_host?: string;
  smtp_port?: number;
  smtp_user?: string;
  smtp_password?: string;
  smtp_use_tls: boolean;
  smtp_from_email?: string;
  smtp_from_name?: string;
  imap_host?: string;
  imap_port?: number;
  imap_user?: string;
  imap_password?: string;
  imap_use_ssl: boolean;
  email_signature?: string;  // HTML signature
  email_test_mode: boolean;
}

export interface UserEmailSettingsUpdate {
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
}

export interface Customer {
  id: number;
  customer_number: string;
  name: string;
  email?: string;
  phone?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  county?: string;
  postcode?: string;
  country?: string;
  customer_since: string;
  created_at: string;
  updated_at: string;
}

export interface Lead {
  id: number;
  name: string;
  email?: string;
  phone?: string;
  postcode?: string;
  description?: string;
  status: LeadStatus;
  timeframe: Timeframe;
  scope_notes?: string;
  product_interest?: string;
  lead_type: LeadType;
  lead_source: LeadSource;
  assigned_to_id?: number;
  customer_id?: number;
  created_at: string;
  updated_at: string;
  sla_badge?: string;
  quote_locked: boolean;
  quote_lock_reason?: {
    error: string;
    missing?: string[];
    message?: string;
  };
  customer?: Customer;
}

export interface Activity {
  id: number;
  customer_id: number;
  activity_type: ActivityType;
  notes?: string;
  created_by_id: number;
  created_at: string;
  created_by_name?: string;
}

export interface StatusHistory {
  id: number;
  lead_id: number;
  old_status?: LeadStatus;
  new_status: LeadStatus;
  changed_by_id: number;
  override_reason?: string;
  created_at: string;
  changed_by_name?: string;
}

export interface DashboardStats {
  total_leads: number;
  new_count: number;
  engaged_count: number;
  qualified_count: number;
  quoted_count: number;
  won_count: number;
  lost_count: number;
  engaged_percentage: number;
  qualified_percentage: number;
}

export interface Product {
  id: number;
  name: string;
  description?: string;
  category: ProductCategory;
  subcategory?: string;
  is_extra: boolean;
  base_price: number;
  unit: string;
  sku?: string;
  is_active: boolean;
  image_url?: string;
  specifications?: string;
  created_at: string;
  updated_at: string;
}

export interface CompanySettings {
  id: number;
  company_name: string;
  company_registration_number?: string;
  vat_number?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  county?: string;
  postcode?: string;
  country: string;
  phone?: string;
  email?: string;
  website?: string;
  logo_filename: string;
  updated_at: string;
}

export enum EmailDirection {
  SENT = "SENT",
  RECEIVED = "RECEIVED",
}

export interface Email {
  id: number;
  customer_id: number;
  message_id?: string;
  in_reply_to?: string;
  thread_id?: string;
  direction: EmailDirection;
  from_email: string;
  to_email: string;
  cc?: string;
  bcc?: string;
  subject: string;
  body_html?: string;
  body_text?: string;
  attachments?: string;
  sent_at?: string;
  received_at?: string;
  created_by_id?: number;
  created_at: string;
  created_by_name?: string;
}

export interface EmailCreate {
  customer_id: number;
  to_email: string;
  cc?: string;
  bcc?: string;
  subject: string;
  body_html?: string;
  body_text?: string;
}

export interface EmailReplyRequest {
  body_html?: string;
  body_text?: string;
  cc?: string;
  bcc?: string;
}

export interface QuoteEmailSendRequest {
  template_id?: number;
  to_email: string;
  cc?: string;
  bcc?: string;
  custom_message?: string;
}

export interface QuoteEmailSendResponse {
  email_id: number;
  quote_email_id: number;
  message: string;
}

export interface EmailTemplate {
  id: number;
  name: string;
  description?: string;
  subject_template: string;
  body_template: string;
  is_default: boolean;
  created_by_id: number;
  created_at: string;
  updated_at: string;
  created_by_name?: string;
}

export interface EmailTemplateCreate {
  name: string;
  description?: string;
  subject_template: string;
  body_template: string;
  is_default?: boolean;
}

export interface EmailTemplateUpdate {
  name?: string;
  description?: string;
  subject_template?: string;
  body_template?: string;
  is_default?: boolean;
}

export interface EmailTemplatePreviewRequest {
  customer_id?: number;
}

export interface EmailTemplatePreviewResponse {
  subject: string;
  body_html: string;
}
