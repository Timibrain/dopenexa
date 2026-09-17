from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LedgerAccount, LedgerEntry, LedgerTransaction


class LedgerError(ValueError):
    """Raised when a ledger transaction cannot be posted safely."""


@dataclass(frozen=True)
class LedgerLine:
    account_code: str
    direction: str
    amount_ngn: int


DEFAULT_ACCOUNTS = {
    "processor_cash_clearing": "Processor / cash clearing",
    "professional_payable": "Professional payable",
    "professional_payable_reserved": "Professional payable reserved",
    "platform_commission": "Platform commission",
}


async def _accounts_for(session: AsyncSession, lines: list[LedgerLine]) -> dict[str, LedgerAccount]:
    codes = {line.account_code for line in lines}
    rows = (await session.scalars(select(LedgerAccount).where(LedgerAccount.code.in_(codes)))).all()
    accounts = {row.code: row for row in rows}
    for code in codes - accounts.keys():
        name = DEFAULT_ACCOUNTS.get(code, code.replace("_", " ").title())
        account = LedgerAccount(code=code, name=name, currency="NGN")
        session.add(account)
        accounts[code] = account
    await session.flush()
    return accounts


def _signature(lines: list[LedgerLine]) -> tuple[tuple[str, str, int], ...]:
    return tuple(sorted((line.account_code, line.direction, line.amount_ngn) for line in lines))


async def _existing_signature(session: AsyncSession, transaction_id: UUID) -> tuple[tuple[str, str, int], ...]:
    rows = (await session.execute(
        select(LedgerAccount.code, LedgerEntry.direction, LedgerEntry.amount_ngn)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .where(LedgerEntry.transaction_id == transaction_id)
    )).all()
    return tuple(sorted((code, direction, amount) for code, direction, amount in rows))


async def post_transaction(
    session: AsyncSession,
    *,
    idempotency_key: str,
    transaction_type: str,
    lines: list[LedgerLine],
    source_type: str | None = None,
    source_id: UUID | None = None,
    currency: str = "NGN",
) -> LedgerTransaction:
    """Post one balanced, immutable ledger transaction in the caller's transaction."""
    if not idempotency_key:
        raise LedgerError("Ledger idempotency key is required")
    if currency != "NGN":
        raise LedgerError("Only NGN ledger postings are supported")
    if not lines:
        raise LedgerError("A ledger transaction needs at least two entries")
    if any(line.direction not in {"debit", "credit"} for line in lines):
        raise LedgerError("Ledger directions must be debit or credit")
    if any(line.amount_ngn <= 0 for line in lines):
        raise LedgerError("Ledger amounts must be positive integer NGN values")
    debit_total = sum(line.amount_ngn for line in lines if line.direction == "debit")
    credit_total = sum(line.amount_ngn for line in lines if line.direction == "credit")
    if debit_total != credit_total:
        raise LedgerError(f"Unbalanced ledger transaction: debits={debit_total}, credits={credit_total}")

    existing = await session.scalar(select(LedgerTransaction).where(LedgerTransaction.idempotency_key == idempotency_key))
    if existing:
        if await _existing_signature(session, existing.id) != _signature(lines):
            raise LedgerError("Ledger idempotency key was reused with different entries")
        return existing

    try:
        async with session.begin_nested():
            accounts = await _accounts_for(session, lines)
            transaction = LedgerTransaction(
                idempotency_key=idempotency_key,
                transaction_type=transaction_type,
                currency=currency,
                source_type=source_type,
                source_id=source_id,
            )
            session.add(transaction)
            await session.flush()
            session.add_all([
                LedgerEntry(
                    transaction_id=transaction.id,
                    account_id=accounts[line.account_code].id,
                    direction=line.direction,
                    amount_ngn=line.amount_ngn,
                )
                for line in lines
            ])
            await session.flush()
        return transaction
    except IntegrityError:
        existing = await session.scalar(select(LedgerTransaction).where(LedgerTransaction.idempotency_key == idempotency_key))
        if existing:
            if await _existing_signature(session, existing.id) != _signature(lines):
                raise LedgerError("Ledger idempotency key was reused with different entries")
            return existing
        raise
