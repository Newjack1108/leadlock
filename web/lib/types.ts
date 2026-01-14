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

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
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
  assigned_to_id?: number;
  created_at: string;
  updated_at: string;
  sla_badge?: string;
  quote_locked: boolean;
  quote_lock_reason?: {
    error: string;
    missing?: string[];
    message?: string;
  };
}

export interface Activity {
  id: number;
  lead_id: number;
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
