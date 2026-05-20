export enum LeadStatus {
  NEW = "NEW",
  CONTACT_ATTEMPTED = "CONTACT_ATTEMPTED",
  ENGAGED = "ENGAGED",
  QUALIFIED = "QUALIFIED",
  QUOTED = "QUOTED",
  WON = "WON",
  LOST = "LOST",
  CLOSED = "CLOSED",
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
  CONFIGURATOR = "CONFIGURATOR",
}

export const CONFIGURATOR_FRONT_FACES = ['top', 'right', 'bottom', 'left'] as const;
export type ConfiguratorFrontFace = (typeof CONFIGURATOR_FRONT_FACES)[number];
export const CONFIGURATOR_CONNECTION_PROFILES = ['corner_left', 'corner_right'] as const;
export type ConfiguratorConnectionProfile = (typeof CONFIGURATOR_CONNECTION_PROFILES)[number];

/** Fixed subcategory labels for catalog filtering and forms (matches Product.subcategory). */
export const PRODUCT_SUBCATEGORIES = [
  "Standard",
  "Extras",
  "Pent",
  "Pony",
  "Professional",
  "Coachman",
  "Bespoke",
  "Other",
] as const;

export type ProductSubcategory = (typeof PRODUCT_SUBCATEGORIES)[number];

export enum LeadType {
  UNKNOWN = "UNKNOWN",
  STABLES = "STABLES",
  SHEDS = "SHEDS",
  CABINS = "CABINS",
}

export enum LeadSource {
  UNKNOWN = "UNKNOWN",
  FACEBOOK = "FACEBOOK",
  FACEBOOK_WHATSAPP = "Facebook/WhatsApp",
  INSTAGRAM = "INSTAGRAM",
  WEBSITE = "WEBSITE",  // Legacy - prefer CSGB/CS/BLC WEBSITE for new leads
  CSGB_WEBSITE = "CSGB WEBSITE",
  CS_WEBSITE = "CS WEBSITE",
  BLC_WEBSITE = "BLC WEBSITE",
  MANUAL_ENTRY = "MANUAL_ENTRY",
  NINOX = "NINOX",
  SMS = "SMS",
  EMAIL = "EMAIL",
  PHONE = "PHONE",
  PAST_CUSTOMER = "Past Customer",
  REFERRAL = "REFERRAL",
  CONFIGURATOR = "CONFIGURATOR",
  OTHER = "OTHER",
}

export type ConfiguratorInviteStatus =
  | "PENDING_DETAILS"
  | "ACTIVE"
  | "SUBMITTED"
  | "EXPIRED";

export interface PublicConfiguratorContext {
  status: ConfiguratorInviteStatus;
  customer_name?: string | null;
  quote_id?: number | null;
  lead_id?: number | null;
  submitted_at?: string | null;
  configuration?: QuoteConfigurationPayload | null;
  customer_postcode?: string | null;
}

export interface ConfiguratorInvite {
  id: number;
  access_token: string;
  configure_url: string;
  status: ConfiguratorInviteStatus;
  quote_id?: number | null;
  lead_id?: number | null;
  customer_id?: number | null;
  customer_name?: string | null;
  created_by_id?: number | null;
  assigned_to_id?: number | null;
  campaign_slug?: string | null;
  submitted_at?: string | null;
  expires_at?: string | null;
  created_at: string;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  can_access_configurator?: boolean;
}

export interface AuthMe {
  id: number;
  email: string;
  full_name: string;
  role: string;
  can_access_configurator: boolean;
}

export interface UserList {
  id: number;
  email: string;
  full_name: string;
  role: string;
  dealer_id?: number | null;
  dealer_commission_pct?: number | null;
  is_active: boolean;
  created_at: string;
}

export interface ConfiguratorAccessStatus {
  enabled: boolean;
  mode: string;
}

export interface ConfiguratorBoxPlacement {
  id: string;
  product_id: number;
  x: number;
  y: number;
  rotation: 0 | 90 | 180 | 270;
}

export interface ConfiguratorExtraSelection {
  product_id: number;
  quantity?: number;
}

export type ConfiguratorDeliveryEstimateInclusion =
  | 'none'
  | 'delivery_only'
  | 'delivery_and_install';

export interface QuoteConfigurationPayload {
  schema_version: number;
  name?: string;
  boxes: ConfiguratorBoxPlacement[];
  extras: ConfiguratorExtraSelection[];
  delivery_estimate_inclusion?: ConfiguratorDeliveryEstimateInclusion;
}

export interface ConfiguratorPreviewRequest {
  configuration: QuoteConfigurationPayload;
  customer_postcode?: string;
}

export interface ConfiguratorValidationIssue {
  code: string;
  severity: 'error' | 'warning';
  message: string;
  box_ids: string[];
}

export interface ConfiguratorGeneratedLine {
  product_id?: number;
  description: string;
  quantity: number;
  unit_price: number;
  is_custom: boolean;
  sort_order: number;
  parent_index?: number;
  include_in_building_discount: boolean;
  line_type?: 'DELIVERY' | 'INSTALLATION' | null;
}

export interface ConfiguratorPreviewResponse {
  valid: boolean;
  issues: ConfiguratorValidationIssue[];
  items: ConfiguratorGeneratedLine[];
  subtotal: number;
  total_boxes: number;
}

export interface ConfiguratorCatalogResponse {
  items: Product[];
  extras: Product[];
}

export interface QuoteConfigurationResponse {
  quote_id: number;
  version: number;
  configuration: QuoteConfigurationPayload;
  created_by_id: number;
  created_at: string;
  updated_at: string;
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
  sms_bot_paused_until?: string | null;
  sms_bot_stopped?: boolean;
  /** When true, background reminder-rule SMS/email is not sent (manual staff messages still allowed). */
  automated_reminder_outreach_opt_out?: boolean;
  /** When true, this address is known bad and automated emails should be suppressed. */
  wrong_email_address?: boolean;
  created_at: string;
  updated_at: string;
  messenger_psid?: string | null;
  source_system?: string | null;
}

export interface CustomerListPayload {
  items: Customer[];
  total: number;
  page: number;
  page_size: number;
}

export interface ChannelDirectionCounts {
  sent: number;
  received: number;
}

export interface CustomerCommunicationStats {
  email: ChannelDirectionCounts;
  sms: ChannelDirectionCounts;
  phone: ChannelDirectionCounts;
  phone_answered: number;
  phone_unanswered: number;
}

export interface Lead {
  id: number;
  name: string;
  email?: string;
  wrong_email_address?: boolean;
  phone?: string;
  postcode?: string;
  description?: string;
  status: LeadStatus;
  timeframe: Timeframe;
  scope_notes?: string;
  product_interest?: string;
  lead_type: LeadType;
  lead_source: LeadSource;
  facebook_advert_profile_id?: number | null;
  facebook_advert_profile?: FacebookAdvertProfile | null;
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
  /** True if any quote for this lead was opened via the customer view link. */
  quote_viewed?: boolean;
  /** True if the customer has inbound email, SMS, or Messenger for this lead/customer. */
  has_inbound_reply?: boolean;
  /** Deal temperature on the most recently updated quote linked to this lead. */
  latest_quote_temperature?: QuoteTemperature | null;
  /** Number of quotes linked to this lead with sent_at set. */
  quotes_sent_count?: number;
  archived_at?: string | null;
}

export interface LeadListPayload {
  items: Lead[];
  total: number;
  page: number;
  page_size: number;
}

export interface LeadHandoverPdfOptions {
  days?: number;
}

export interface FacebookAdvertProfile {
  id: number;
  name: string;
  offer_type?: string;
  image_url?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
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

export interface LeadSourceCount {
  source: string;
  count: number;
}

export interface LeadLocationItem {
  lat: number;
  lng: number;
  postcode: string;
  count: number;
}

export type DashboardPresetPeriod = 'all' | 'week' | 'month' | 'quarter' | 'year';

export interface DateRangeQueryParams {
  period?: DashboardPresetPeriod;
  start_date?: string;
  end_date?: string;
}

export interface DashboardStats {
  total_leads: number;
  new_count: number;
  engaged_count: number;
  qualified_count: number;
  quoted_count: number;
  quotes_sent_count: number;
  leads_with_sent_quotes_count: number;
  won_count: number;
  lost_count: number;
  closed_count: number;
  engaged_percentage: number;
  qualified_percentage: number;
  leads_by_source: LeadSourceCount[];
}

export interface DashboardChannelDirectionCounts {
  sent: number;
  received: number;
}

export interface DashboardCommunicationTotals {
  period: string;
  start_date: string;
  end_date: string;
  email: DashboardChannelDirectionCounts;
  sms: DashboardChannelDirectionCounts;
  phone: DashboardChannelDirectionCounts;
  phone_answered: number;
  phone_unanswered: number;
  email_reply_rate_pct: number;
  sms_reply_rate_pct: number;
  total_sent: number;
  total_received: number;
  total: number;
}

export interface QualifiedForQuotingItem {
  id: number;
  name: string;
  customer_name: string | null;
  updated_at: string;
  assigned_to_id: number | null;
}

export interface QualifiedForQuotingSummary {
  count: number;
  leads: QualifiedForQuotingItem[];
}

// Sales Report types
export interface PipelineValueStageItem {
  stage: string;
  count: number;
  total_value: number;
  weighted_value: number;
}

export interface PipelineValueReport {
  period?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  generated_at: string;
  stages: PipelineValueStageItem[];
  total_value: number;
  total_weighted_value: number;
}

export interface SourcePerformanceItem {
  source: string;
  leads_count: number;
  quoted_count: number;
  won_count: number;
  conversion_rate: number;
}

export interface SourcePerformanceReport {
  period?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  generated_at: string;
  sources: SourcePerformanceItem[];
  total_leads: number;
}

export interface FacebookLeadConversionSummary {
  total_facebook_leads: number;
  converted_leads: number;
  conversion_rate: number;
  total_orders: number;
  total_order_revenue: number;
  average_order_value: number;
  average_days_to_convert: number;
  unknown_advert_profile_leads: number;
  won_without_order_leads: number;
}

export interface FacebookLeadConversionBreakdownItem {
  name: string;
  leads_count: number;
  converted_leads: number;
  conversion_rate: number;
  total_orders: number;
  total_revenue: number;
  average_order_value: number;
  average_days_to_convert: number;
}

export interface FacebookLeadConversionRow {
  lead_id: number;
  lead_created_at: string;
  lead_name: string;
  email?: string | null;
  phone?: string | null;
  lead_status: string;
  lead_source: string;
  advert_profile_name: string;
  product_interest?: string | null;
  lead_type: string;
  product_type: string;
  quote_number?: string | null;
  order_number?: string | null;
  order_created_at?: string | null;
  order_amount?: number | null;
  days_to_convert?: number | null;
  converted: boolean;
  order_count: number;
  won_without_order: boolean;
}

export interface FacebookLeadConversionReport {
  period?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  generated_at: string;
  summary: FacebookLeadConversionSummary;
  advert_breakdown: FacebookLeadConversionBreakdownItem[];
  product_type_breakdown: FacebookLeadConversionBreakdownItem[];
  rows: FacebookLeadConversionRow[];
}

export interface CloserPerformanceItem {
  user_id: number;
  full_name: string;
  leads_assigned: number;
  won_count: number;
  total_revenue: number;
}

export interface CloserPerformanceReport {
  generated_at: string;
  closers: CloserPerformanceItem[];
}

export interface QuoteEngagementReport {
  period?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  generated_at: string;
  sent_count: number;
  viewed_count: number;
  not_opened_count: number;
  viewed_no_reply_count: number;
  accepted_count: number;
  rejected_count: number;
}

export interface WeeklyPipelineSummaryReport {
  week_label: string;
  generated_at: string;
  new_count: number;
  quoted_count: number;
  won_count: number;
  lost_count: number;
  closed_count: number;
  start_date: string;
  end_date: string;
}

export interface Product {
  id: number;
  name: string;
  description?: string;
  category: ProductCategory;
  subcategory?: string;
  is_extra: boolean;
  allow_trade_dealer_sale: boolean;
  base_price: number;
  unit: string;
  sku?: string;
  is_active: boolean;
  image_url?: string;
  specifications?: string;
  size?: string;
  height?: string;
  floor_plan_url?: string;
  width?: number;
  length?: number;
  configurator_width?: number;
  configurator_length?: number;
  configurator_front_face?: ConfiguratorFrontFace | null;
  configurator_connection_profile?: ConfiguratorConnectionProfile | null;
  configurator_is_corner_box?: boolean;
  configurator_is_starter_box?: boolean;
  allow_in_configurator: boolean;
  configurator_per_box?: boolean;
  installation_hours?: number;
  boxes_per_product?: number;
  is_production_synced: boolean;
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

export enum SmsBotMode {
  OFF = "OFF",
  AUTO = "AUTO",
  ON = "ON",
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
  footer_logo_url?: string;
  default_terms_and_conditions?: string;
  email_disclaimer?: string;
  default_email_signature?: string;
  hourly_install_rate?: number;
  installation_lead_time?: InstallationLeadTime;
  installation_lead_time_stables?: InstallationLeadTime;
  installation_lead_time_sheds?: InstallationLeadTime;
  installation_lead_time_cabins?: InstallationLeadTime;
  distance_before_overnight_miles?: number;
  cost_per_mile?: number;
  hotel_allowance_per_night?: number;
  meal_allowance_per_day?: number;
  average_speed_mph?: number;
  install_quote_margin_pct?: number;
  product_import_gross_margin_pct?: number;
  sms_bot_mode?: SmsBotMode;
  sms_bot_timezone?: string;
  sms_bot_business_hours_json?: string;
  sms_bot_fallback_message?: string;
  sms_bot_max_replies_per_thread?: number;
  sms_bot_pause_minutes_after_handover?: number;
  sms_bot_system_instructions?: string | null;
  bank_name?: string;
  bank_account_name?: string;
  account_number?: string;
  sort_code?: string;
  require_engagement_proof?: boolean;
  updated_at: string;
}

export interface DeliveryInstallEstimateRequest {
  customer_postcode: string;
  installation_hours: number;
  number_of_boxes?: number;
  delivery_only?: boolean;
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
  delivery_only?: boolean;
  delivery_trips?: number;
  number_of_boxes?: number;
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
  read_at?: string | null;
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

export enum SmsSenderKind {
  CUSTOMER = "customer",
  SMS_BOT = "sms_bot",
  SYSTEM = "system",
  USER = "user",
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
  sender_kind?: SmsSenderKind;
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

export interface SalesDocument {
  id: number;
  name: string;
  filename: string;
  content_type?: string;
  file_size?: number;
  category?: string;
  created_at?: string;
}

export interface QuoteEmailSendRequest {
  template_id: number;
  to_email: string;
  cc?: string;
  bcc?: string;
  custom_message?: string;
  include_available_extras?: boolean;
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


export interface WeeklyPlanTemplate {
  id: number;
  name: string;
  description?: string;
  suggested_action: SuggestedAction;
  channel: string;
  subject_template?: string | null;
  body_template: string;
  is_active: boolean;
  created_by_id: number;
  created_at: string;
  updated_at: string;
  created_by_name?: string | null;
}

export interface WeeklyPlanTemplateCreate {
  name: string;
  description?: string;
  suggested_action: SuggestedAction;
  channel: string;
  subject_template?: string;
  body_template: string;
  is_active?: boolean;
}

export interface WeeklyPlanTemplateUpdate {
  name?: string;
  description?: string;
  suggested_action?: SuggestedAction;
  channel?: string;
  subject_template?: string;
  body_template?: string;
  is_active?: boolean;
}

export interface WeeklyPlanTemplatePreviewResponse {
  subject?: string | null;
  body: string;
}

export interface WeeklyPlanBulkSendResult {
  message: string;
  requested: number;
  sent: number;
  failed: number;
}

export interface QuoteTemplateAttachedDocument {
  id: number;
  name: string;
  filename: string;
  sort_order: number;
}

export interface QuoteTemplate {
  id: number;
  name: string;
  description?: string;
  email_subject_template: string;
  email_body_template: string;
  is_default: boolean;
  created_by_id: number;
  created_at: string;
  created_by_name?: string;
  attached_documents?: QuoteTemplateAttachedDocument[];
}

export interface QuoteTemplateCreate {
  name: string;
  description?: string;
  email_subject_template: string;
  email_body_template: string;
  is_default?: boolean;
  sales_document_ids?: number[];
}

export interface QuoteTemplateUpdate {
  name?: string;
  description?: string;
  email_subject_template?: string;
  email_body_template?: string;
  is_default?: boolean;
  sales_document_ids?: number[];
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
  /** When false, line is excluded from PRODUCT-scope (“building items only”) discounts */
  include_in_building_discount?: boolean | null;
  /** Per-unit install hours for custom lines */
  installation_hours?: number | null;
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
  /** Default true; set false to exclude from “building items only” discounts */
  include_in_building_discount?: boolean;
  /** Per-unit install hours for custom lines */
  installation_hours?: number;
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
  lead_type?: LeadType | null;
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
  /** Stored one-way drive time (hours); production webhook sends 2× as round-trip when set */
  travel_time_hours_one_way?: number | null;
  is_ninox_origin?: boolean;
  items: OrderItem[];
  access_sheet?: AccessSheet | null;
}

export enum CustomerFileKind {
  PLAN = "PLAN",
  PHOTO = "PHOTO",
  OTHER = "OTHER",
}

export interface CustomerFile {
  id: number;
  customer_id: number;
  quote_id?: number | null;
  order_id?: number | null;
  kind: CustomerFileKind;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  secure_url: string;
  uploaded_by_id: number;
  uploaded_by_name?: string | null;
  created_at: string;
}

export interface Quote {
  id: number;
  customer_id: number | null;
  customer_name?: string;
  lead_id?: number | null;
  lead_name?: string | null;
  lead_type?: LeadType | null;
  quote_number: string;
  version: number;
  status: QuoteStatus;
  subtotal: number;
  discount_total: number;
  total_amount: number;
  /** Deposit amount inc VAT */
  deposit_amount: number;
  /** Balance amount inc VAT */
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
  include_spec_sheets?: boolean;
  /** Show extras not yet on the quote in customer online view and PDF */
  include_available_optional_extras?: boolean;
  /** Footer note: delivery/installation contact (SMS, email, phone) below totals */
  include_delivery_installation_contact_note?: boolean;
  total_open_count?: number;
  order_id?: number | null;
  customer_last_interacted_at?: string | null;
  archived_at?: string | null;
  dealer_customer_name?: string | null;
  dealer_customer_email?: string | null;
  dealer_customer_phone?: string | null;
  dealer_customer_address?: string | null;
  dealer_customer_postcode?: string | null;
  /** Quotes on this lead with sent_at (paginated list only). */
  lead_quotes_sent_count?: number | null;
  customer_replied_since_quote_sent?: boolean;
  inbound_count_since_quote_sent?: number;
}

export interface QuoteListPayload {
  items: Quote[];
  total: number;
  page: number;
  page_size: number;
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
  bank_name?: string;
  bank_account_name?: string;
  sort_code?: string;
  account_number?: string;
}

export interface AvailableExtraResponse {
  name: string;
  base_price: number;
}

/** Named discount line on quotation (matches template/custom discount name). */
export interface PublicQuoteDiscountLine {
  description: string;
  discount_amount: number;
}

export interface PublicLayoutBox {
  id: string;
  label: string;
  x: number;
  y: number;
  rotation: 0 | 90 | 180 | 270;
  width: number;
  length: number;
  is_corner_box: boolean;
  front_face?: ConfiguratorFrontFace;
  connection_profile?: ConfiguratorConnectionProfile;
  blocked_front_m?: number | null;
}

export interface PublicQuoteLayout {
  name?: string | null;
  boxes: PublicLayoutBox[];
}

export interface PublicQuoteView {
  quote_number: string;
  order_number?: string | null;
  customer_name: string;
  currency: string;
  valid_until?: string;
  subtotal: number;
  discount_total: number;
  discount_lines?: PublicQuoteDiscountLine[];
  total_amount: number;
  /** Deposit amount inc VAT */
  deposit_amount: number;
  /** Balance amount inc VAT */
  balance_amount: number;
  vat_amount?: number;
  total_amount_inc_vat?: number;
  items: PublicQuoteViewItem[];
  terms_and_conditions?: string;
  company_display?: PublicQuoteCompanyDisplay;
  available_optional_extras?: AvailableExtraResponse[];
  /** Full message when quote opts in; omitted when disabled */
  delivery_installation_contact_note?: string | null;
  layout?: PublicQuoteLayout | null;
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
  max_uses?: number | null;
  expires_at?: string | null;
  usage_count?: number;
  remaining_uses?: number | null;
  created_at: string;
  updated_at: string;
}

export interface DiscountTemplateCreate {
  name: string;
  description?: string;
  discount_type: DiscountType;
  discount_value: number;
  scope: DiscountScope;
  is_giveaway?: boolean;
  max_uses?: number | null;
  expires_at?: string | null;
}

export interface DiscountTemplateUpdate {
  name?: string;
  description?: string;
  discount_type?: DiscountType;
  discount_value?: number;
  scope?: DiscountScope;
  is_active?: boolean;
  is_giveaway?: boolean;
  max_uses?: number | null;
  expires_at?: string | null;
}

/** True if the template has an expiry time in the past (hide from quote discount picker). */
export function isDiscountTemplateExpired(d: Pick<DiscountTemplate, 'expires_at'>): boolean {
  if (!d.expires_at) return false;
  return new Date(d.expires_at).getTime() < Date.now();
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
  USER_TASK = "USER_TASK",
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
  due_date?: string;
  created_by_id?: number;
  created_by_name?: string;
  assigned_to_name?: string;
  /** Latest customer auto-outreach (SMS/email) for this reminder's lead or quote */
  auto_outreach_status?: string | null;
  auto_outreach_channel?: string | null;
  auto_outreach_sent_at?: string | null;
  auto_outreach_failure_reason?: string | null;
  auto_outreach_rule_name?: string | null;
}

export interface AssignableUser {
  id: number;
  full_name: string;
  email: string;
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

export interface AutomatedReminderCleanupResult {
  deleted_count: number;
  deleted_ids: number[];
}

export interface ReminderRule {
  id: number;
  rule_name: string;
  entity_type: string;
  status: string | null;
  threshold_minutes: number;
  check_type: string;
  is_active: boolean;
  priority: ReminderPriority;
  suggested_action: SuggestedAction;
  created_at: string;
  updated_at: string;
  customer_outreach_channel?: string | null;
  customer_outreach_sms_template_id?: number | null;
  customer_outreach_email_template_id?: number | null;
  customer_outreach_cooldown_days?: number;
  customer_outreach_on_lead_create?: boolean;
}

export interface ReminderRuleUpdate {
  threshold_minutes?: number;
  is_active?: boolean;
  priority?: ReminderPriority;
  suggested_action?: SuggestedAction;
  customer_outreach_channel?: string | null;
  customer_outreach_sms_template_id?: number | null;
  customer_outreach_email_template_id?: number | null;
  customer_outreach_cooldown_days?: number | null;
  customer_outreach_on_lead_create?: boolean | null;
}

export interface ReminderRuleCreate {
  rule_name: string;
  entity_type: 'LEAD' | 'QUOTE';
  status?: string | null;
  threshold_minutes: number;
  check_type: string;
  is_active: boolean;
  priority: ReminderPriority;
  suggested_action: SuggestedAction;
  customer_outreach_channel?: string | null;
  customer_outreach_sms_template_id?: number | null;
  customer_outreach_email_template_id?: number | null;
  customer_outreach_cooldown_days?: number | null;
  customer_outreach_on_lead_create?: boolean | null;
}

export type OutreachSendChannel = 'SMS' | 'EMAIL';
export type OutreachSendTargetType = 'LEAD' | 'QUOTE';

export interface OutreachSendListItem {
  id: number;
  reminder_rule_id: number;
  reminder_rule_name: string;
  customer_id: number;
  customer_name?: string | null;
  channel: OutreachSendChannel;
  target_type: OutreachSendTargetType;
  lead_id?: number | null;
  lead_name?: string | null;
  quote_id?: number | null;
  quote_number?: string | null;
  external_message_id?: string | null;
  status: 'SENT' | 'FAILED' | string;
  failure_reason?: string | null;
  sent_at: string;
}

export interface OutreachSendListResponse {
  items: OutreachSendListItem[];
  total: number;
  page: number;
  page_size: number;
}

export enum WeeklyPlanItemStatus {
  PENDING_REVIEW = "PENDING_REVIEW",
  AUTO_SENT = "AUTO_SENT",
  REJECTED = "REJECTED",
  COMPLETED = "COMPLETED",
  AUTO_FAILED = "AUTO_FAILED",
}

export interface WeeklyPlanRun {
  id: number;
  week_start: string;
  generated_at: string;
  scope: string;
  model_version: string;
  generated_by_id?: number | null;
  total_items: number;
  auto_eligible_items: number;
  auto_sent_items: number;
}

export interface WeeklyPlanItem {
  id: number;
  plan_run_id: number;
  lead_id?: number | null;
  quote_id?: number | null;
  customer_id?: number | null;
  assigned_to_id?: number | null;
  assigned_to_name?: string | null;
  customer_name?: string | null;
  quote_number?: string | null;
  lead_name?: string | null;
  priority_score: number;
  confidence: number;
  order_likelihood_score: number;
  order_likelihood_confidence: number;
  order_likelihood_reasons: string[];
  likelihood_explanation?: string | null;
  recommended_next_steps: string[];
  reason_codes: string[];
  recommended_action: SuggestedAction;
  channel?: string | null;
  status: WeeklyPlanItemStatus;
  auto_eligible: boolean;
  suggested_message?: string | null;
  due_date?: string | null;
  executed_at?: string | null;
  execution_error?: string | null;
  outcome_result?: string | null;
  response_received: boolean;
  created_at: string;
  updated_at: string;
}

export interface WeeklyPlanListResponse {
  run: WeeklyPlanRun;
  items: WeeklyPlanItem[];
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
  ORDER_CREATED = "ORDER_CREATED",
  ORDER_REMOVED = "ORDER_REMOVED",
  ORDER_PAYMENT_UPDATED = "ORDER_PAYMENT_UPDATED",
  ORDER_INSTALLATION_UPDATED = "ORDER_INSTALLATION_UPDATED",
  ORDER_ACCESS_SHEET_SENT = "ORDER_ACCESS_SHEET_SENT",
  ORDER_ACCESS_SHEET_COMPLETED = "ORDER_ACCESS_SHEET_COMPLETED",
  ORDER_SENT_TO_PRODUCTION = "ORDER_SENT_TO_PRODUCTION",
  ORDER_XERO_PUSHED = "ORDER_XERO_PUSHED",
  ORDER_INVOICE_ACTION = "ORDER_INVOICE_ACTION",
}

export interface CustomerHistoryEvent {
  event_type: CustomerHistoryEventType;
  timestamp: string;
  title: string;
  description?: string;
  metadata?: Record<string, unknown>;
  created_by_name?: string;
  created_by_id?: number;
}

export interface CustomerHistoryResponse {
  events: CustomerHistoryEvent[];
}

export interface DealerWelcome {
  dealer_id: number;
  dealer_name: string;
  user_id: number;
  user_name: string;
  commission_pct: number;
}

export interface DealerQuoteProductItem {
  product_id: number;
  quantity: number;
  selected_extra_ids?: number[];
}

export type DealerDeliveryEstimateInclusion =
  | 'none'
  | 'delivery_only'
  | 'delivery_and_install';

export interface DealerQuoteCreatePayload {
  customer_name: string;
  customer_email?: string;
  customer_phone?: string;
  customer_address?: string;
  customer_postcode?: string;
  delivery_estimate_inclusion?: DealerDeliveryEstimateInclusion;
  notes?: string;
  valid_until?: string;
  product_items: DealerQuoteProductItem[];
  discount_template_ids?: number[];
}

export interface DealerAllowedDiscountPolicy {
  mode: string;
  allow_fixed_amount: boolean;
  allow_percentage: boolean;
  max_discount_percentage?: number | null;
  max_discount_amount?: number | null;
  allowed_discount_template_ids: number[];
}

export interface DealerSummary {
  id: number;
  name: string;
  company_name?: string | null;
  is_active: boolean;
}

export interface DealerDiscountPolicyAdminPayload {
  mode: string;
  allow_fixed_amount: boolean;
  allow_percentage: boolean;
  max_discount_percentage?: number | null;
  max_discount_amount?: number | null;
  allowed_discount_template_ids: number[];
}

export interface DealerDiscountPolicyAdminResponse extends DealerDiscountPolicyAdminPayload {
  dealer_id: number;
}

export interface DealerProfile {
  id: number;
  name: string;
  company_name?: string;
  contact_name?: string;
  email?: string;
  phone?: string;
  address?: string;
  vat_number?: string;
  registration_number?: string;
  website?: string;
  logo_url?: string;
  is_active: boolean;
}

export interface DealerProfileUpdatePayload {
  name?: string;
  company_name?: string;
  contact_name?: string;
  email?: string;
  phone?: string;
  address?: string;
  vat_number?: string;
  registration_number?: string;
  website?: string;
}
