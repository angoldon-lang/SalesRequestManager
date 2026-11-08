import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY, BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric,
    SmallInteger, String, Text, text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _enum(cls, name):
    return Enum(cls, name=name, create_type=False)


class RequestType(str, enum.Enum):
    NUOVO = "NUOVO"
    DR = "DR"


class RequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    REMINDED = "REMINDED"
    CLOSED = "CLOSED"


class CloseReason(str, enum.Enum):
    WON = "WON"
    LOST = "LOST"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    NO_RESPONSE = "NO_RESPONSE"


class RequestSource(str, enum.Enum):
    MANUAL = "MANUAL"
    EMAIL_AI = "EMAIL_AI"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"            # Admin / Direzione Sales
    BACKOFFICE = "BACKOFFICE"
    SALES = "SALES"


class InboundStatus(str, enum.Enum):
    NEW = "NEW"
    PARSED = "PARSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ERROR = "ERROR"
    IGNORED = "IGNORED"


NOW = text("now()")


class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entra_oid: Mapped[str | None] = mapped_column(UUID(as_uuid=False), unique=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "user_role"), default=UserRole.SALES)
    sales_agent_id: Mapped[int | None] = mapped_column(ForeignKey("sales_agents.id", ondelete="SET NULL"), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class SalesAgent(Base):
    __tablename__ = "sales_agents"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    website: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class VendorSupplierMap(Base):
    __tablename__ = "vendor_supplier_map"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    to_emails: Mapped[list[str]] = mapped_column(ARRAY(Text))
    cc_emails: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    supports_dr: Mapped[bool] = mapped_column(Boolean, default=True)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)


class GlobalConfig(Base):
    __tablename__ = "global_config"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    sender_email: Mapped[str] = mapped_column(CITEXT)
    inbound_mailbox: Mapped[str] = mapped_column(CITEXT)
    inbound_processed_folder: Mapped[str] = mapped_column(Text, default="SRM-Processed")
    default_cc: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    reminder_after_days: Mapped[int] = mapped_column(SmallInteger, default=3)
    reminder_max_count: Mapped[int] = mapped_column(SmallInteger, default=3)
    reminder_business_days: Mapped[bool] = mapped_column(Boolean, default=True)
    llm_model: Mapped[str] = mapped_column(Text, default="claude-sonnet-5-5")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class InboundEmail(Base):
    __tablename__ = "inbound_emails"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    graph_message_id: Mapped[str] = mapped_column(Text, unique=True)
    internet_msg_id: Mapped[str | None] = mapped_column(Text)
    from_email: Mapped[str] = mapped_column(CITEXT)
    subject: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[InboundStatus] = mapped_column(
        _enum(InboundStatus, "inbound_status"), default=InboundStatus.NEW)
    llm_raw_output: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Request(Base):
    __tablename__ = "requests"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, server_default=text(
        "'SRM-' || to_char(now(),'YYYY') || '-' || lpad(nextval('request_code_seq')::text, 5, '0')"))
    request_type: Mapped[RequestType] = mapped_column(_enum(RequestType, "request_type"))
    status: Mapped[RequestStatus] = mapped_column(
        _enum(RequestStatus, "request_status"), default=RequestStatus.DRAFT)
    source: Mapped[RequestSource] = mapped_column(
        _enum(RequestSource, "request_source"), default=RequestSource.MANUAL)

    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    sales_agent_id: Mapped[int | None] = mapped_column(ForeignKey("sales_agents.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))

    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    product_description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int | None] = mapped_column(Integer)

    end_customer_name: Mapped[str | None] = mapped_column(Text)
    estimated_deal_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    vendor_dr_reference: Mapped[str | None] = mapped_column(Text)
    dr_approved_at: Mapped[date | None] = mapped_column(Date)
    dr_expires_at: Mapped[date | None] = mapped_column(Date)

    graph_message_id: Mapped[str | None] = mapped_column(Text)
    graph_conversation_id: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    first_vendor_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[CloseReason | None] = mapped_column(_enum(CloseReason, "close_reason"))

    inbound_email_id: Mapped[int | None] = mapped_column(ForeignKey("inbound_emails.id"))
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)

    vendor: Mapped[Vendor | None] = relationship(lazy="joined")
    supplier: Mapped[Supplier | None] = relationship(lazy="joined")
    sales_agent: Mapped[SalesAgent | None] = relationship(lazy="joined")


class RequestEvent(Base):
    __tablename__ = "request_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
