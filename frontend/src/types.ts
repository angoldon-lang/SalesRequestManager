export type RequestType = "NUOVO" | "DR";
export type RequestStatus = "DRAFT" | "SENT" | "REMINDED" | "CLOSED";
export type CloseReason = "WON" | "LOST" | "APPROVED" | "REJECTED" | "CANCELLED" | "NO_RESPONSE";

export interface Req {
  id: number; code: string; request_type: RequestType; status: RequestStatus;
  source: "MANUAL" | "EMAIL_AI";
  vendor_id: number | null; supplier_id: number | null; sales_agent_id: number | null;
  vendor_name: string | null; supplier_name: string | null; agent_name: string | null;
  subject: string; body: string | null; product_description: string | null; quantity: number | null;
  end_customer_name: string | null; estimated_deal_value: string | null; currency: string;
  expected_close_date: string | null; vendor_dr_reference: string | null;
  dr_approved_at: string | null; dr_expires_at: string | null;
  sent_at: string | null; last_reminder_at: string | null; reminder_count: number;
  first_vendor_reply_at: string | null; closed_at: string | null; close_reason: CloseReason | null;
  ai_confidence: string | null; needs_review: boolean; inbound_email_id: number | null;
  created_at: string;
}
export interface Vendor { id: number; name: string; website: string | null; notes: string | null; is_active: boolean }
export interface Supplier { id: number; name: string; notes: string | null; is_active: boolean }
export interface Agent { id: number; full_name: string; email: string; is_active: boolean }
export interface MapRow {
  id: number; vendor_id: number; supplier_id: number; to_emails: string[]; cc_emails: string[];
  supports_dr: boolean; is_preferred: boolean;
}
export interface Config {
  sender_email: string; inbound_mailbox: string; inbound_processed_folder: string; default_cc: string[];
  reminder_after_days: number; reminder_max_count: number; reminder_business_days: boolean; llm_model: string;
}
export interface User { id: number; email: string; full_name: string; role: "ADMIN" | "OPERATOR"; is_active: boolean }
export interface Inbound {
  id: number; from_email: string; subject: string | null; body_text: string | null; received_at: string;
  status: string; llm_raw_output: Record<string, unknown> | null; error_message: string | null;
}
export interface EventRow { id: number; event_type: string; actor: string; payload: Record<string, unknown> | null; created_at: string }

export const STATUS_LABEL: Record<RequestStatus, string> = {
  DRAFT: "Bozza", SENT: "Inviata", REMINDED: "Sollecitata", CLOSED: "Chiusa",
};
export const REASON_LABEL: Record<CloseReason, string> = {
  WON: "Vinta", LOST: "Persa", APPROVED: "Approvata", REJECTED: "Rifiutata",
  CANCELLED: "Annullata", NO_RESPONSE: "Nessuna risposta",
};
