from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import CloseReason, InboundStatus, RequestSource, RequestStatus, RequestType, UserRole


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _lower_list(v):
    return [e.strip().lower() for e in v if e and e.strip()]


# ---------- anagrafiche ----------
class VendorIn(BaseModel):
    name: str = Field(min_length=1)
    website: str | None = None
    notes: str | None = None
    is_active: bool = True


class VendorOut(VendorIn, ORM):
    id: int


class SupplierIn(BaseModel):
    name: str = Field(min_length=1)
    notes: str | None = None
    is_active: bool = True


class SupplierOut(SupplierIn, ORM):
    id: int


class AgentOut(ORM):
    """Agente commerciale = utente con ruolo SALES."""
    id: int
    full_name: str
    email: str | None
    is_active: bool


class MapIn(BaseModel):
    vendor_id: int
    supplier_id: int
    to_emails: list[EmailStr] = Field(min_length=1)
    cc_emails: list[EmailStr] = []
    supports_dr: bool = True
    is_preferred: bool = False

    @field_validator("to_emails", "cc_emails")
    @classmethod
    def lower(cls, v):
        return _lower_list(v)


class MapOut(ORM):
    id: int
    vendor_id: int
    supplier_id: int
    to_emails: list[str]
    cc_emails: list[str]
    supports_dr: bool
    is_preferred: bool


class UserOut(ORM):
    id: int
    username: str
    email: str | None
    full_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool = False
    last_login_at: datetime | None = None
    locked_until: datetime | None = None
    has_password: bool = True


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._@+-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    role: UserRole = UserRole.SALES
    password: str = Field(min_length=1, max_length=128)       # provvisoria: l'utente deve cambiarla al primo accesso
    is_active: bool = True

    @field_validator("email", mode="before")
    @classmethod
    def empty_email(cls, v):
        return v or None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("email", mode="before")
    @classmethod
    def empty_email(cls, v):
        return v or None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=1, max_length=128)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool
    user: UserOut


# ---------- config ----------
class ConfigIn(BaseModel):
    sender_email: EmailStr
    inbound_mailbox: EmailStr
    inbound_processed_folder: str = "SRM-Processed"
    default_cc: list[EmailStr] = []
    reminder_after_days: int = Field(ge=1, le=60)
    reminder_max_count: int = Field(ge=1, le=10)
    reminder_business_days: bool = True
    llm_model: str

    @field_validator("default_cc")
    @classmethod
    def lower(cls, v):
        return _lower_list(v)


class ConfigOut(ORM):
    sender_email: str
    inbound_mailbox: str
    inbound_processed_folder: str
    default_cc: list[str]
    reminder_after_days: int
    reminder_max_count: int
    reminder_business_days: bool
    llm_model: str
    updated_at: datetime


# ---------- richieste ----------
class RequestFields(BaseModel):
    vendor_id: int | None = None
    supplier_id: int | None = None
    sales_agent_id: int | None = None
    subject: str | None = Field(default=None, min_length=1)
    body: str | None = None
    product_description: str | None = None
    quantity: int | None = Field(default=None, gt=0)
    end_customer_name: str | None = None
    estimated_deal_value: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    expected_close_date: date | None = None
    needs_review: bool | None = None


class RequestCreate(RequestFields):
    request_type: RequestType
    subject: str = Field(min_length=1)


class RequestPatch(RequestFields):
    request_type: RequestType | None = None
    vendor_dr_reference: str | None = None
    dr_approved_at: date | None = None
    dr_expires_at: date | None = None


class CloseIn(BaseModel):
    reason: CloseReason
    vendor_dr_reference: str | None = None
    dr_approved_at: date | None = None
    dr_expires_at: date | None = None


class NamedRef(ORM):
    id: int
    name: str | None = None
    full_name: str | None = None


class RequestOut(ORM):
    id: int
    code: str
    request_type: RequestType
    status: RequestStatus
    source: RequestSource
    vendor_id: int | None
    supplier_id: int | None
    sales_agent_id: int | None
    vendor_name: str | None = None
    supplier_name: str | None = None
    agent_name: str | None = None
    subject: str
    body: str | None
    product_description: str | None
    quantity: int | None
    end_customer_name: str | None
    estimated_deal_value: Decimal | None
    currency: str
    expected_close_date: date | None
    vendor_dr_reference: str | None
    dr_approved_at: date | None
    dr_expires_at: date | None
    sent_at: datetime | None
    last_reminder_at: datetime | None
    reminder_count: int
    first_vendor_reply_at: datetime | None
    closed_at: datetime | None
    close_reason: CloseReason | None
    ai_confidence: Decimal | None
    needs_review: bool
    inbound_email_id: int | None
    created_at: datetime
    updated_at: datetime


class RequestPage(BaseModel):
    items: list[RequestOut]
    total: int


class EventOut(ORM):
    id: int
    event_type: str
    actor: str
    payload: dict | None
    created_at: datetime


class InboundOut(ORM):
    id: int
    from_email: str
    subject: str | None
    body_text: str | None
    received_at: datetime
    status: InboundStatus
    llm_raw_output: dict | None
    error_message: str | None
    processed_at: datetime | None
