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
  MESSENGER_SENT = "MESSENGER_SENT",
  MESSENGER_RECEIVED = "MESSENGER_RECEIVED",
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

export interface WebsiteVisit {
  site: string;
  visited_at: string;
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
  messenger_psid?: string | null;
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
  installation_hours?: number;
  boxes_per_product?: number;
  optional_extras?: Product[];
  created_at: string;
  updated_at: string;
}

export enum InstallationLeadTime {
  ONE_TWO_WEEKS = '1-2 weeks',
  TWO_THREE_WEEKS = '2-3 weeks',
  THREE_FOUR_WEEKS = '3-4 weeks',
  FOUR_FIVE_WEEKS = '4-5 weeks',
  FIVE_SIX_WEEKS = '5-6 weeks',
}

export interface CompanySettings {
  id: number;
  company_name: string;
  trading_name?: string;
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
  logo_url?: string;
  default_terms_and_conditions?: string;
  hourly_install_rate?: number;
  installation_lead_time?: InstallationLeadTime;
  distance_before_overnight_miles?: number;
  cost_per_mile?: number;
  hotel_allowance_per_night?: number;
  meal_allowance_per_day?: number;
  average_speed_mph?: number;
  product_import_gross_margin_pct?: number;
  updated_at: string;
}

export interface DeliveryInstallEstimateRequest {
  customer_postcode: string;
  installation_hours: number;
  number_of_boxes?: number;
}

export interface DeliveryInstallEstimateResponse {
  distance_miles: number;
  travel_time_hours_one_way: number;
  fitting_days: number;
  requires_overnight: boolean;
  nights_away: number;
  cost_mileage?: number;
  cost_labour?: number;
  cost_hotel?: number;
  cost_meals?: number;
  cost_total: number;
  settings_incomplete: boolean;
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

export enum SmsDirection {
  SENT = "SENT",
  RECEIVED = "RECEIVED",
}

export interface SmsMessage {
  id: number;
  customer_id: number;
  lead_id?: number;
  direction: SmsDirection;
  from_phone: string;
  to_phone: string;
  body: string;
  twilio_sid?: string;
  sent_at?: string;
  received_at?: string;
  read_at?: string | null;
  created_by_id?: number;
  created_at: string;
  created_by_name?: string;
}

export interface UnreadSmsMessageItem {
  id: number;
  customer_id: number;
  customer_name: string;
  body: string;
  received_at: string | null;
  from_phone: string;
}

export interface UnreadSmsSummary {
  count: number;
  messages: UnreadSmsMessageItem[];
}

export enum MessengerDirection {
  SENT = "SENT",
  RECEIVED = "RECEIVED",
}

export interface MessengerMessage {
  id: number;
  customer_id: number;
  lead_id?: number | null;
  direction: MessengerDirection;
  from_psid: string;
  to_psid?: string | null;
  body: string;
  facebook_mid?: string | null;
  sent_at?: string | null;
  received_at?: string | null;
  read_at?: string | null;
  created_by_id?: number | null;
  created_at: string;
  created_by_name?: string | null;
}

export interface UnreadMessengerMessageItem {
  id: number;
  customer_id: number;
  customer_name: string;
  body: string;
  received_at: string | null;
  from_psid: string;
}

export interface UnreadMessengerSummary {
  count: number;
  messages: UnreadMessengerMessageItem[];
}

export interface SmsCreate {
  customer_id: number;
  to_phone?: string;
  body: string;
  lead_id?: number;
}

export enum ScheduledSmsStatus {
  PENDING = "PENDING",
  SENT = "SENT",
  CANCELLED = "CANCELLED",
}

export interface SmsScheduled {
  id: number;
  customer_id: number;
  to_phone: string;
  body: string;
  scheduled_at: string;
  status: ScheduledSmsStatus;
  created_by_id: number;
  created_at: string;
  sent_at?: string;
  twilio_sid?: string;
}

export interface SmsScheduledCreate {
  customer_id: number;
  to_phone: string;
  body: string;
  scheduled_at: string;
}

export interface SmsScheduledUpdate {
  scheduled_at?: string;
  status?: ScheduledSmsStatus;
}

export interface SmsTemplate {
  id: number;
  name: string;
  description?: string;
  body_template: string;
  is_default: boolean;
  created_by_id: number;
  created_at: string;
  updated_at: string;
  created_by_name?: string;
}

export interface SmsTemplateCreate {
  name: string;
  description?: string;
  body_template: string;
  is_default?: boolean;
}

export interface SmsTemplateUpdate {
  name?: string;
  description?: string;
  body_template?: string;
  is_default?: boolean;
}

export interface SmsTemplatePreviewRequest {
  customer_id?: number;
}

export interface SmsTemplatePreviewResponse {
  body: string;
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
  view_url?: string;
  test_mode?: boolean;
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

export enum QuoteStatus {
  DRAFT = "DRAFT",
  SENT = "SENT",
  VIEWED = "VIEWED",
  ACCEPTED = "ACCEPTED",
  REJECTED = "REJECTED",
  EXPIRED = "EXPIRED",
}

export enum QuoteTemperature {
  HOT = "HOT",
  WARM = "WARM",
  COLD = "COLD",
}

export enum DiscountType {
  FIXED_AMOUNT = "FIXED_AMOUNT",
  PERCENTAGE = "PERCENTAGE",
}

export enum DiscountScope {
  PRODUCT = "PRODUCT",
  QUOTE = "QUOTE",
}

export enum OpportunityStage {
  DISCOVERY = "DISCOVERY",
  CONCEPT = "CONCEPT",
  QUOTE_SENT = "QUOTE_SENT",
  FOLLOW_UP = "FOLLOW_UP",
  DECISION_PENDING = "DECISION_PENDING",
  WON = "WON",
  LOST = "LOST",
}

export enum LossCategory {
  PRICE = "PRICE",
  TIMING = "TIMING",
  COMPETITOR = "COMPETITOR",
  PLANNING = "PLANNING",
  OTHER = "OTHER",
}

export type QuoteItemLineType = 'DELIVERY' | 'INSTALLATION';

export interface QuoteItem {
  id: number;
  quote_id: number;
  product_id?: number;
  description: string;
  quantity: number;
  unit_price: number;
  line_total: number;
  discount_amount: number;
  final_line_total: number;
  sort_order: number;
  is_custom: boolean;
  parent_quote_item_id?: number | null;
  line_type?: QuoteItemLineType | null;
}

export interface QuoteItemCreate {
  product_id?: number;
  description: string;
  quantity: number;
  unit_price: number;
  is_custom?: boolean;
  sort_order?: number;
  parent_index?: number | null;
  line_type?: QuoteItemLineType | null;
}

export interface OrderItem {
  id: number;
  order_id: number;
  quote_item_id?: number | null;
  product_id?: number | null;
  description: string;
  quantity: number;
  unit_price: number;
  line_total: number;
  discount_amount: number;
  final_line_total: number;
  sort_order: number;
  is_custom: boolean;
}

/** Access sheet status and data shown on order page */
export interface AccessSheet {
  access_sheet_url?: string | null;
  completed: boolean;
  completed_at?: string | null;
  answers?: Record<string, string> | null;
}

export interface Order {
  id: number;
  quote_id: number;
  customer_id?: number | null;
  customer_name?: string | null;
  order_number: string;
  subtotal: number;
  discount_total: number;
  total_amount: number;
  deposit_amount: number;
  balance_amount: number;
  currency: string;
  terms_and_conditions?: string | null;
  notes?: string | null;
  created_by_id: number;
  created_at: string;
  deposit_paid?: boolean;
  balance_paid?: boolean;
  paid_in_full?: boolean;
  installation_booked?: boolean;
  installation_completed?: boolean;
  invoice_number?: string | null;
  xero_invoice_id?: string | null;
  items: OrderItem[];
  access_sheet?: AccessSheet | null;
}

export interface Quote {
  id: number;
  customer_id: number;
  customer_name?: string;
  quote_number: string;
  version: number;
  status: QuoteStatus;
  subtotal: number;
  discount_total: number;
  total_amount: number;
  deposit_amount: number;
  balance_amount: number;
  currency: string;
  /** Computed: VAT @ 20% on total_amount (Ex VAT). */
  vat_amount?: number;
  /** Computed: total_amount + vat_amount. */
  total_amount_inc_vat?: number;
  deposit_amount_inc_vat?: number;
  balance_amount_inc_vat?: number;
  valid_until?: string;
  terms_and_conditions?: string;
  notes?: string;
  created_by_id: number;
  sent_at?: string;
  viewed_at?: string;   // First viewed at
  last_viewed_at?: string;
  accepted_at?: string;
  created_at: string;
  updated_at: string;
  items: QuoteItem[];
  discounts?: QuoteDiscount[];
  // Opportunity fields
  opportunity_stage?: OpportunityStage;
  close_probability?: number;
  expected_close_date?: string;
  next_action?: string;
  next_action_due_date?: string;
  loss_reason?: string;
  loss_category?: LossCategory;
  owner_id?: number;
  temperature?: QuoteTemperature;
  total_open_count?: number;
  order_id?: number | null;
}

/** Public quote view (no auth) - for customer view link. */
export interface PublicQuoteViewItem {
  description: string;
  quantity: number;
  unit_price: number;
  line_total: number;
  final_line_total: number;
  sort_order: number;
}

/** Company display for public quote header (logo + contact). */
export interface PublicQuoteCompanyDisplay {
  trading_name?: string;
  logo_url?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  county?: string;
  postcode?: string;
  phone?: string;
  email?: string;
  website?: string;
}

export interface PublicQuoteView {
  quote_number: string;
  customer_name: string;
  currency: string;
  valid_until?: string;
  subtotal: number;
  discount_total: number;
  total_amount: number;
  deposit_amount: number;
  balance_amount: number;
  vat_amount?: number;
  total_amount_inc_vat?: number;
  items: PublicQuoteViewItem[];
  terms_and_conditions?: string;
  company_display?: PublicQuoteCompanyDisplay;
}

export interface QuoteCreate {
  customer_id: number;
  quote_number?: string;
  version?: number;
  valid_until?: string;
  terms_and_conditions?: string;
  notes?: string;
  deposit_amount?: number;
  items: QuoteItemCreate[];
  discount_template_ids?: number[];
  temperature?: QuoteTemperature;
}

export interface DiscountTemplate {
  id: number;
  name: string;
  description?: string;
  discount_type: DiscountType;
  discount_value: number;
  scope: DiscountScope;
  is_active: boolean;
  is_giveaway: boolean;
  created_at: string;
  updated_at: string;
  usage_count?: number;
}

export interface DiscountTemplateCreate {
  name: string;
  description?: string;
  discount_type: DiscountType;
  discount_value: number;
  scope: DiscountScope;
  is_giveaway?: boolean;
}

export interface DiscountTemplateUpdate {
  name?: string;
  description?: string;
  discount_type?: DiscountType;
  discount_value?: number;
  scope?: DiscountScope;
  is_active?: boolean;
  is_giveaway?: boolean;
}

export interface QuoteDiscount {
  id: number;
  quote_id: number;
  quote_item_id?: number;
  template_id?: number;
  discount_type: DiscountType;
  discount_value: number;
  scope: DiscountScope;
  discount_amount: number;
  description: string;
  applied_at: string;
  applied_by_id: number;
}

export enum DiscountRequestStatus {
  PENDING = "PENDING",
  APPROVED = "APPROVED",
  REJECTED = "REJECTED",
}

export interface DiscountRequest {
  id: number;
  quote_id: number;
  requested_by_id: number;
  requested_by_name?: string;
  discount_type: DiscountType;
  discount_value: number;
  scope: DiscountScope;
  reason?: string;
  status: DiscountRequestStatus;
  approved_by_id?: number;
  responded_at?: string;
  rejection_reason?: string;
  created_at: string;
  updated_at: string;
  quote_number?: string;
}

export interface DiscountRequestCreate {
  discount_type: DiscountType;
  discount_value: number;
  scope: DiscountScope;
  reason?: string;
}

export enum ReminderPriority {
  LOW = "LOW",
  MEDIUM = "MEDIUM",
  HIGH = "HIGH",
  URGENT = "URGENT",
}

export enum ReminderType {
  LEAD_STALE = "LEAD_STALE",
  QUOTE_STALE = "QUOTE_STALE",
  QUOTE_EXPIRING = "QUOTE_EXPIRING",
  QUOTE_EXPIRED = "QUOTE_EXPIRED",
  QUOTE_NOT_OPENED = "QUOTE_NOT_OPENED",
  QUOTE_OPENED_NO_REPLY = "QUOTE_OPENED_NO_REPLY",
  MANUAL = "MANUAL",
}

export enum SuggestedAction {
  FOLLOW_UP = "FOLLOW_UP",
  MARK_LOST = "MARK_LOST",
  RESEND_QUOTE = "RESEND_QUOTE",
  REVIEW_QUOTE = "REVIEW_QUOTE",
  CONTACT_CUSTOMER = "CONTACT_CUSTOMER",
  PHONE_CALL = "PHONE_CALL",
}

export interface Reminder {
  id: number;
  reminder_type: ReminderType;
  lead_id?: number;
  quote_id?: number;
  customer_id?: number;
  assigned_to_id: number;
  priority: ReminderPriority;
  title: string;
  message: string;
  suggested_action: SuggestedAction;
  days_stale: number;
  created_at: string;
  dismissed_at?: string;
  acted_upon_at?: string;
  lead_name?: string;
  quote_number?: string;
  customer_name?: string;
}

export interface StaleSummary {
  total_reminders: number;
  urgent_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  stale_leads_count: number;
  stale_quotes_count: number;
}

export enum CustomerHistoryEventType {
  ACTIVITY = "ACTIVITY",
  LEAD_STATUS_CHANGE = "LEAD_STATUS_CHANGE",
  QUOTE_CREATED = "QUOTE_CREATED",
  QUOTE_SENT = "QUOTE_SENT",
  QUOTE_VIEWED = "QUOTE_VIEWED",
  QUOTE_ACCEPTED = "QUOTE_ACCEPTED",
  QUOTE_REJECTED = "QUOTE_REJECTED",
  QUOTE_EXPIRED = "QUOTE_EXPIRED",
  QUOTE_UPDATED = "QUOTE_UPDATED",
  EMAIL_SENT = "EMAIL_SENT",
  EMAIL_RECEIVED = "EMAIL_RECEIVED",
  CUSTOMER_CREATED = "CUSTOMER_CREATED",
  CUSTOMER_UPDATED = "CUSTOMER_UPDATED",
  LEAD_QUALIFIED = "LEAD_QUALIFIED",
  OPPORTUNITY_CREATED = "OPPORTUNITY_CREATED",
}

export interface CustomerHistoryEvent {
  event_type: CustomerHistoryEventType;
  timestamp: string;
  title: string;
  description?: string;
  metadata?: Record<string, any>;
  created_by_name?: string;
  created_by_id?: number;
}

export interface CustomerHistoryResponse {
  events: CustomerHistoryEvent[];
}
