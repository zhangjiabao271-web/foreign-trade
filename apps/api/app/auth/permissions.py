from collections.abc import Mapping
from enum import StrEnum

from app.identity.enums import MembershipRole


class Permission(StrEnum):
    ORGANIZATION_MANAGE = "organization.manage"
    MEMBER_MANAGE = "member.manage"
    OPERATIONS_MONITOR = "operations.monitor"
    COMPANY_READ = "company.read"
    COMPANY_WRITE = "company.write"
    LEAD_READ = "lead.read"
    LEAD_WRITE = "lead.write"
    LEAD_CONVERT = "lead.convert"
    OPPORTUNITY_READ = "opportunity.read"
    OPPORTUNITY_WRITE = "opportunity.write"
    INQUIRY_READ = "inquiry.read"
    INQUIRY_WRITE = "inquiry.write"
    PRODUCT_READ = "product.read"
    PRODUCT_WRITE = "product.write"
    PRODUCT_SUPPLIER_READ = "product_supplier.read"
    PRODUCT_SUPPLIER_WRITE = "product_supplier.write"
    QUOTATION_READ = "quotation.read"
    QUOTATION_WRITE = "quotation.write"
    QUOTATION_SUBMIT = "quotation.submit"
    QUOTATION_APPROVE = "quotation.approve"
    QUOTATION_SEND = "quotation.send"
    QUOTATION_ACCEPT = "quotation.accept"
    ORDER_READ = "order.read"
    CONTRACT_READ = "contract.read"
    CONTRACT_WRITE = "contract.write"
    CONTRACT_SIGN = "contract.sign"
    ORDER_WRITE = "order.write"
    ORDER_CONFIRM = "order.confirm"
    ORDER_COMPLETE = "order.complete"
    ORDER_FINANCE_WAIVE = "order.finance_waive"
    PROCUREMENT_READ = "procurement.read"
    PROCUREMENT_WRITE = "procurement.write"
    PROCUREMENT_APPROVE = "procurement.approve"
    SHIPMENT_READ = "shipment.read"
    SHIPMENT_WRITE = "shipment.write"
    SHIPMENT_TRANSITION = "shipment.transition"
    DOCUMENT_READ = "document.read"
    DOCUMENT_WRITE = "document.write"
    RECEIVABLE_READ = "receivable.read"
    RECEIVABLE_WRITE = "receivable.write"
    PAYMENT_READ = "payment.read"
    PAYMENT_RECORD = "payment.record"
    PAYMENT_ALLOCATE = "payment.allocate"
    PAYMENT_REVERSE = "payment.reverse"
    EXPENSE_READ = "expense.read"
    EXPENSE_WRITE = "expense.write"
    PAYABLE_READ = "payable.read"
    PAYABLE_WRITE = "payable.write"
    SUPPLIER_PAYMENT_READ = "supplier_payment.read"
    SUPPLIER_PAYMENT_RECORD = "supplier_payment.record"
    SUPPLIER_PAYMENT_ALLOCATE = "supplier_payment.allocate"
    SUPPLIER_PAYMENT_REVERSE = "supplier_payment.reverse"
    EXPORT_READ = "export.read"
    EXPORT_WRITE = "export.write"
    TASK_READ = "task.read"
    TASK_WRITE = "task.write"
    OVERVIEW_READ = "overview.read"
    PROFIT_READ = "profit.read"
    AUDIT_READ = "audit.read"
    JOB_READ = "job.read"
    JOB_CREATE = "job.create"
    OUTBOX_READ = "outbox.read"
    OUTBOX_REPLAY = "outbox.replay"
    AI_READ = "ai.read"
    AI_RUN = "ai.run"
    AI_APPROVE = "ai.approve"


READ_PERMISSIONS = frozenset(
    {
        Permission.COMPANY_READ,
        Permission.LEAD_READ,
        Permission.OPPORTUNITY_READ,
        Permission.INQUIRY_READ,
        Permission.PRODUCT_READ,
        Permission.PRODUCT_SUPPLIER_READ,
        Permission.QUOTATION_READ,
        Permission.ORDER_READ,
        Permission.CONTRACT_READ,
        Permission.PROCUREMENT_READ,
        Permission.SHIPMENT_READ,
        Permission.DOCUMENT_READ,
        Permission.RECEIVABLE_READ,
        Permission.PAYMENT_READ,
        Permission.EXPORT_READ,
        Permission.TASK_READ,
        Permission.OVERVIEW_READ,
        Permission.PROFIT_READ,
        Permission.AUDIT_READ,
        Permission.JOB_READ,
        Permission.OUTBOX_READ,
        Permission.AI_READ,
    }
)

MANAGER_COMMAND_PERMISSIONS = frozenset(
    {
        Permission.COMPANY_WRITE,
        Permission.LEAD_WRITE,
        Permission.LEAD_CONVERT,
        Permission.OPPORTUNITY_WRITE,
        Permission.INQUIRY_WRITE,
        Permission.PRODUCT_WRITE,
        Permission.PRODUCT_SUPPLIER_WRITE,
        Permission.QUOTATION_WRITE,
        Permission.QUOTATION_SUBMIT,
        Permission.QUOTATION_APPROVE,
        Permission.QUOTATION_SEND,
        Permission.QUOTATION_ACCEPT,
        Permission.ORDER_WRITE,
        Permission.CONTRACT_WRITE,
        Permission.CONTRACT_SIGN,
        Permission.ORDER_CONFIRM,
        Permission.ORDER_COMPLETE,
        Permission.ORDER_FINANCE_WAIVE,
        Permission.PROCUREMENT_WRITE,
        Permission.PROCUREMENT_APPROVE,
        Permission.SHIPMENT_WRITE,
        Permission.SHIPMENT_TRANSITION,
        Permission.DOCUMENT_WRITE,
        Permission.RECEIVABLE_WRITE,
        Permission.PAYMENT_RECORD,
        Permission.PAYMENT_ALLOCATE,
        Permission.PAYMENT_REVERSE,
        Permission.EXPENSE_READ,
        Permission.EXPENSE_WRITE,
        Permission.PAYABLE_READ,
        Permission.PAYABLE_WRITE,
        Permission.SUPPLIER_PAYMENT_READ,
        Permission.SUPPLIER_PAYMENT_RECORD,
        Permission.SUPPLIER_PAYMENT_ALLOCATE,
        Permission.SUPPLIER_PAYMENT_REVERSE,
        Permission.EXPORT_WRITE,
        Permission.TASK_WRITE,
        Permission.JOB_CREATE,
        Permission.OUTBOX_REPLAY,
        Permission.AI_RUN,
        Permission.AI_APPROVE,
    }
)

ROLE_PERMISSIONS: Mapping[MembershipRole, frozenset[Permission]] = {
    MembershipRole.ADMIN: frozenset(Permission),
    MembershipRole.MANAGER: READ_PERMISSIONS | MANAGER_COMMAND_PERMISSIONS,
    MembershipRole.SALES: (
        READ_PERMISSIONS
        | {
            Permission.COMPANY_WRITE,
            Permission.LEAD_WRITE,
            Permission.LEAD_CONVERT,
            Permission.OPPORTUNITY_WRITE,
            Permission.INQUIRY_WRITE,
            Permission.QUOTATION_WRITE,
            Permission.QUOTATION_SUBMIT,
            Permission.QUOTATION_SEND,
            Permission.QUOTATION_ACCEPT,
            Permission.ORDER_WRITE,
            Permission.CONTRACT_WRITE,
            Permission.TASK_WRITE,
            Permission.JOB_CREATE,
            Permission.AI_RUN,
        }
    )
    - {
        Permission.AUDIT_READ,
        Permission.OUTBOX_READ,
        Permission.PROFIT_READ,
        Permission.PRODUCT_SUPPLIER_READ,
    },
    MembershipRole.OPERATIONS: (
        READ_PERMISSIONS
        | {
            Permission.COMPANY_WRITE,
            Permission.PROCUREMENT_WRITE,
            Permission.SHIPMENT_WRITE,
            Permission.SHIPMENT_TRANSITION,
            Permission.DOCUMENT_WRITE,
            Permission.EXPORT_WRITE,
            Permission.TASK_WRITE,
            Permission.JOB_CREATE,
            Permission.AI_RUN,
        }
    )
    - {
        Permission.AUDIT_READ,
        Permission.OUTBOX_READ,
        Permission.PROFIT_READ,
        Permission.PRODUCT_SUPPLIER_READ,
    },
    MembershipRole.FINANCE: (
        READ_PERMISSIONS
        | {
            Permission.RECEIVABLE_WRITE,
            Permission.PAYMENT_RECORD,
            Permission.PAYMENT_ALLOCATE,
            Permission.PAYMENT_REVERSE,
            Permission.EXPENSE_READ,
            Permission.EXPENSE_WRITE,
            Permission.PAYABLE_READ,
            Permission.PAYABLE_WRITE,
            Permission.SUPPLIER_PAYMENT_READ,
            Permission.SUPPLIER_PAYMENT_RECORD,
            Permission.SUPPLIER_PAYMENT_ALLOCATE,
            Permission.SUPPLIER_PAYMENT_REVERSE,
            Permission.TASK_WRITE,
            Permission.JOB_CREATE,
            Permission.AI_RUN,
        }
    )
    - {Permission.AUDIT_READ, Permission.OUTBOX_READ},
    MembershipRole.VIEWER: READ_PERMISSIONS
    - {
        Permission.PRODUCT_SUPPLIER_READ,
        Permission.AUDIT_READ,
        Permission.OUTBOX_READ,
        Permission.PROFIT_READ,
        Permission.JOB_READ,
    },
}


def permissions_for_role(role: MembershipRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]
