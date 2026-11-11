import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def record_audit(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None,
    actor_type: str,
    actor_user_id: uuid.UUID | None = None,
    data: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        data=data or {},
    )
    session.add(log)
    return log
