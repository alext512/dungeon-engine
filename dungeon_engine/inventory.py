"""Runtime helpers for entity-owned stack inventories."""

from __future__ import annotations

import copy
from typing import Any, Literal

from dungeon_engine.world.entity import InventoryStack, InventoryState


QuantityMode = Literal["atomic", "partial"]


def serialize_inventory_state(inventory: InventoryState | None) -> dict[str, Any] | None:
    """Return one JSON-friendly plain-data inventory payload."""
    if inventory is None:
        return None
    return {
        "max_stacks": int(inventory.max_stacks),
        "stacks": [
            {
                "item_id": str(stack.item_id),
                "quantity": int(stack.quantity),
            }
            for stack in inventory.stacks
        ],
    }


def clone_inventory_state(inventory: InventoryState | None) -> InventoryState | None:
    """Return one detached inventory copy."""
    if inventory is None:
        return None
    return InventoryState(
        max_stacks=int(inventory.max_stacks),
        stacks=[
            InventoryStack(
                item_id=str(stack.item_id),
                quantity=int(stack.quantity),
            )
            for stack in inventory.stacks
        ],
    )


def inventory_item_count(inventory: InventoryState | None, item_id: str) -> int:
    """Return the total quantity for one item id across all stacks."""
    if inventory is None:
        return 0
    resolved_item_id = str(item_id).strip()
    if not resolved_item_id:
        return 0
    return sum(
        int(stack.quantity)
        for stack in inventory.stacks
        if str(stack.item_id) == resolved_item_id
    )


def inventory_stack_count(inventory: InventoryState | None) -> int:
    """Return the number of occupied stacks in one inventory."""
    if inventory is None:
        return 0
    return len(inventory.stacks)


def inventory_has_item(
    inventory: InventoryState | None,
    item_id: str,
    *,
    quantity: int = 1,
) -> bool:
    """Return True when the inventory contains at least the requested quantity."""
    requested_quantity = max(0, int(quantity))
    return inventory_item_count(inventory, item_id) >= requested_quantity


def normalize_quantity_mode(quantity_mode: str) -> QuantityMode:
    """Validate one public inventory quantity mode."""
    resolved_quantity_mode = str(quantity_mode).strip().lower()
    if resolved_quantity_mode not in {"atomic", "partial"}:
        raise ValueError("quantity_mode must be 'atomic' or 'partial'.")
    return resolved_quantity_mode  # type: ignore[return-value]


def make_inventory_change_result(
    *,
    success: bool,
    item_id: str,
    requested_quantity: int,
    changed_quantity: int,
    remaining_quantity: int,
) -> dict[str, Any]:
    """Return one stable result payload for inventory item operations."""
    return {
        "success": bool(success),
        "item_id": str(item_id),
        "requested_quantity": int(requested_quantity),
        "changed_quantity": int(changed_quantity),
        "remaining_quantity": int(remaining_quantity),
    }


def add_inventory_item_to_state(
    inventory: InventoryState | None,
    *,
    item_id: str,
    quantity: int,
    max_stack: int,
    quantity_mode: QuantityMode,
) -> dict[str, Any]:
    """Add one quantity to an inventory according to the requested mode."""
    requested_quantity = int(quantity)
    if inventory is None:
        return make_inventory_change_result(
            success=False,
            item_id=item_id,
            requested_quantity=requested_quantity,
            changed_quantity=0,
            remaining_quantity=requested_quantity,
        )

    resolved_item_id = str(item_id).strip()
    if not resolved_item_id:
        raise ValueError("add_inventory_item requires a non-empty item_id.")
    if requested_quantity <= 0:
        raise ValueError("add_inventory_item quantity must be positive.")
    resolved_max_stack = int(max_stack)
    if resolved_max_stack <= 0:
        raise ValueError("add_inventory_item max_stack must be positive.")

    normalized_mode = normalize_quantity_mode(quantity_mode)
    if normalized_mode == "atomic" and _inventory_add_capacity(inventory, resolved_item_id, resolved_max_stack) < requested_quantity:
        return make_inventory_change_result(
            success=True,
            item_id=resolved_item_id,
            requested_quantity=requested_quantity,
            changed_quantity=0,
            remaining_quantity=requested_quantity,
        )

    remaining_quantity = requested_quantity
    for stack in inventory.stacks:
        if str(stack.item_id) != resolved_item_id:
            continue
        available_space = resolved_max_stack - int(stack.quantity)
        if available_space <= 0:
            continue
        added_quantity = min(remaining_quantity, available_space)
        stack.quantity += int(added_quantity)
        remaining_quantity -= int(added_quantity)
        if remaining_quantity <= 0:
            break

    while remaining_quantity > 0 and len(inventory.stacks) < int(inventory.max_stacks):
        added_quantity = min(remaining_quantity, resolved_max_stack)
        inventory.stacks.append(
            InventoryStack(
                item_id=resolved_item_id,
                quantity=int(added_quantity),
            )
        )
        remaining_quantity -= int(added_quantity)

    changed_quantity = requested_quantity - remaining_quantity
    return make_inventory_change_result(
        success=True,
        item_id=resolved_item_id,
        requested_quantity=requested_quantity,
        changed_quantity=changed_quantity,
        remaining_quantity=remaining_quantity,
    )


def remove_inventory_item_from_state(
    inventory: InventoryState | None,
    *,
    item_id: str,
    quantity: int,
    quantity_mode: QuantityMode,
) -> dict[str, Any]:
    """Remove one quantity from an inventory according to the requested mode."""
    requested_quantity = int(quantity)
    if inventory is None:
        return make_inventory_change_result(
            success=False,
            item_id=item_id,
            requested_quantity=requested_quantity,
            changed_quantity=0,
            remaining_quantity=requested_quantity,
        )

    resolved_item_id = str(item_id).strip()
    if not resolved_item_id:
        raise ValueError("remove_inventory_item requires a non-empty item_id.")
    if requested_quantity <= 0:
        raise ValueError("remove_inventory_item quantity must be positive.")

    normalized_mode = normalize_quantity_mode(quantity_mode)
    available_quantity = inventory_item_count(inventory, resolved_item_id)
    if normalized_mode == "atomic" and available_quantity < requested_quantity:
        return make_inventory_change_result(
            success=True,
            item_id=resolved_item_id,
            requested_quantity=requested_quantity,
            changed_quantity=0,
            remaining_quantity=requested_quantity,
        )

    removable_quantity = min(requested_quantity, available_quantity)
    remaining_to_remove = removable_quantity
    for index in range(len(inventory.stacks) - 1, -1, -1):
        stack = inventory.stacks[index]
        if str(stack.item_id) != resolved_item_id:
            continue
        removed_quantity = min(int(stack.quantity), remaining_to_remove)
        stack.quantity -= int(removed_quantity)
        remaining_to_remove -= int(removed_quantity)
        if stack.quantity <= 0:
            inventory.stacks.pop(index)
        if remaining_to_remove <= 0:
            break

    changed_quantity = removable_quantity
    return make_inventory_change_result(
        success=True,
        item_id=resolved_item_id,
        requested_quantity=requested_quantity,
        changed_quantity=changed_quantity,
        remaining_quantity=requested_quantity - changed_quantity,
    )


def set_inventory_max_stacks_on_state(
    inventory: InventoryState | None,
    *,
    max_stacks: int,
) -> bool:
    """Set one inventory capacity when it can be applied safely."""
    if inventory is None:
        return False
    resolved_max_stacks = int(max_stacks)
    if resolved_max_stacks < 0:
        raise ValueError("set_inventory_max_stacks max_stacks must be zero or positive.")
    if resolved_max_stacks < len(inventory.stacks):
        return False
    inventory.max_stacks = resolved_max_stacks
    return True


def _inventory_add_capacity(
    inventory: InventoryState,
    item_id: str,
    max_stack: int,
) -> int:
    """Return how much of one item could fit into the current inventory."""
    capacity = 0
    for stack in inventory.stacks:
        if str(stack.item_id) != item_id:
            continue
        capacity += max(0, int(max_stack) - int(stack.quantity))
    free_stack_count = max(0, int(inventory.max_stacks) - len(inventory.stacks))
    capacity += free_stack_count * int(max_stack)
    return capacity
