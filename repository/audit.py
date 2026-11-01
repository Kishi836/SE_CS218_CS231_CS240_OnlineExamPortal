"""FR-030: The one writer of the append-only audit trail."""

import json

from django.core.serializers.json import DjangoJSONEncoder

from .models import AuditEntry


def snapshot(obj, fields):
    """Return the current values of the specified fields."""
    return {field: getattr(obj, field) for field in fields}


def changed(before, after):
    """Return old/new pairs for fields whose values changed."""
    return {
        field: [before[field], after[field]]
        for field in after
        if before.get(field) != after[field]
    }


def record(actor, action, obj, changes=None):
    """Append one AuditEntry and return it.

    actor: authenticated user or None for system actions.
    action: short description of the operation.
    obj: affected model instance.
    changes: optional dictionary describing the changes.
    """
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None

    serializable_changes = json.loads(
        json.dumps(changes or {}, cls=DjangoJSONEncoder)
    )

    return AuditEntry.objects.create(
        actor=actor,
        action=action,
        entity=type(obj).__name__,
        entity_id=obj.pk,
        changes=serializable_changes,
    )