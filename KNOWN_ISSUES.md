# Known Issues / Bugs

## No currently confirmed open issues in the starter room

The two most recent bugs were both fixed. They are kept here because they explain two easy-to-misunderstand parts of the data flow.

## 1. Template lever instances could save stale `interact_commands` into room JSON (fixed)

**Status:** Fixed

**What was wrong:** A normal template entity instance is only supposed to save authored data such as the template id and its parameter values. Instead, a lever instance could also save a fully resolved command list back into the room JSON.

**Why that was bad:** The room file could end up saying two different things at once:

```json
{
  "template": "lever",
  "parameters": {
    "target_gate": "gate_1"
  },
  "interact_commands": [
    {
      "type": "set_visible",
      "entity_id": "",
      "visible": false
    }
  ]
}
```

In that broken example, the authored parameter says `gate_1`, but the saved command override still says `""`. The loader was reading the JSON correctly, but it was reading bad saved data.

**What caused it:** If a lever was first placed while `target_gate` was blank and later retargeted, the editor updated the parameter text but did not rebuild the already-generated live command list before save.

**Fix applied:**
- Parameter edits now rebuild the template instance in memory so generated fields stay in sync with the current parameters.
- Normal template-entity saves no longer write generated fields like `interact_commands` back into room JSON.
- The starter room's stale second-lever override was cleaned up.

**What correct room JSON looks like now:**

```json
{
  "template": "lever",
  "parameters": {
    "target_gate": "gate_1"
  }
}
```

## 2. Play mode auto-wrote a save file during normal play (fixed)

**Status:** Fixed

**What was wrong:** Play mode used to track live persistent changes and immediately flush them to `saves/slot_1.json`, even when the user had not chosen to save yet.

**Current behavior:**
- The room and entity data load from JSON first.
- If `saves/slot_1.json` exists, it is layered on top as an override.
- Live persistent changes are still tracked during play, but only in memory.
- `F5` writes the current persistent state to disk.
- `F9` reloads the save slot from disk.

## 3. Text edit not auto-committed on Save (fixed)

**Status:** Fixed

Clicking the Save toolbar button or pressing Ctrl+S while a property text field was being edited would save without committing the pending text input. The parameter value on the entity would still be the old value.

**Fix applied:** `_commit_text_edit()` is now called before save in both the Ctrl+S handler and on mouse clicks outside the right panel.
