# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
MarkConflict — trademark conflict screening by GenLayer validator consensus.

A submitter proposes a new trademark plus the Nice class it would register
under, and the list of existing marks already living in that class. `check`
asks every validator to independently decide whether the proposed mark is
confusingly similar to any existing mark — judged on PHONETIC similarity (how
it sounds out loud) and SEMANTIC similarity (what it means) WITHIN the same
class. The decision is accepted only when validators agree on the boolean
`conflict` verdict (comparative equivalence on `conflict`), not on the wording
of the reasoning or which mark they name as closest.

The decisive field is `conflict` (bool): does the proposed mark collide with an
existing one? Offending mark and reasoning are advisory; the consensus output
is the yes/no collision call.
"""
import json
from genlayer import *

MAX_EXISTING = 50


def _coerce_bool(v) -> bool:
    """Deterministically coerce an LLM 'conflict' value to a strict bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):          # ints (1/0) but bool already handled above
        return v != 0
    if isinstance(v, float):
        return v != 0.0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "y", "1", "conflict", "confusing", "similar")
    return False


def normalize_check(raw) -> dict:
    """Coerce any LLM payload into a valid verdict; never raises.

    normalize_check({}) -> {"conflict": False, "offending": "none",
                            "reasoning": "no reasoning"}  (conservative default).
    """
    if not isinstance(raw, dict):
        raw = {}
    conflict = _coerce_bool(raw.get("conflict", False))
    offending = raw.get("offending", "none")
    if not isinstance(offending, str) or not offending.strip():
        offending = "none"
    reasoning = raw.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning = "no reasoning"
    return {
        "conflict": conflict,
        "offending": offending.strip()[:200],
        "reasoning": reasoning.strip()[:600],
    }


def validate_check(data) -> bool:
    """Enforce the verdict invariants: strict bool conflict, non-empty strings."""
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("conflict"), bool):
        return False
    off = data.get("offending")
    if not isinstance(off, str) or not off.strip():
        return False
    r = data.get("reasoning")
    return isinstance(r, str) and bool(r.strip())


class MarkConflict(gl.Contract):
    marks: TreeMap[str, str]
    mark_count: u256
    checked_count: u256
    conflict_count: u256

    def __init__(self):
        self.mark_count = u256(0)
        self.checked_count = u256(0)
        self.conflict_count = u256(0)

    # -------------------------------------------------------------- submit
    @gl.public.write
    def submit_mark(self, proposed: str, nice_class: str, existing: list) -> str:
        """Register a proposed mark + its Nice class + existing marks to screen against."""
        proposed = str(proposed).strip()
        nice_class = str(nice_class).strip()
        if not proposed:
            raise Exception("proposed mark required")
        if not nice_class:
            raise Exception("nice_class required")
        if not isinstance(existing, list):
            raise Exception("existing must be a list")
        cleaned = [str(e).strip()[:120] for e in existing if str(e).strip()][:MAX_EXISTING]
        key = str(int(self.mark_count))
        rec = {
            "submitter": str(gl.message.sender_address),
            "proposed": proposed[:200],
            "nice_class": nice_class[:120],
            "existing": cleaned,
            "state": "open",          # open -> checked
            "conflict": False,
            "offending": "",
            "reasoning": "",
        }
        self.marks[key] = json.dumps(rec)
        self.mark_count += u256(1)
        return key

    # -------------------------------------------------------------- check
    @gl.public.write
    def check(self, mark_id: str) -> dict:
        """Consensus decides whether the proposed mark conflicts with existing ones."""
        mark_id = str(mark_id)
        if mark_id not in self.marks:
            raise Exception("unknown mark")
        m = json.loads(self.marks[mark_id])
        if m["state"] != "open":
            raise Exception("mark already checked")

        result = self._check(m["proposed"], m["nice_class"], m["existing"])
        m["conflict"] = result["conflict"]
        m["offending"] = result["offending"]
        m["reasoning"] = result["reasoning"]
        m["state"] = "checked"
        self.marks[mark_id] = json.dumps(m)
        self.checked_count += u256(1)
        if result["conflict"]:
            self.conflict_count += u256(1)
        return {"mark": mark_id, "conflict": result["conflict"], "offending": result["offending"]}

    def _check(self, proposed: str, nice_class: str, existing) -> dict:
        listing = "\n".join(f"- {e}" for e in existing) if existing else "(none provided)"

        def do_check() -> str:
            prompt = f"""You are an impartial trademark examiner. Decide whether the PROPOSED mark conflicts with any EXISTING mark registered in the SAME Nice class.

Consider both:
- PHONETIC similarity — does it sound confusingly alike when spoken?
- SEMANTIC similarity — does it mean / evoke the same thing?

Only marks within the same class can conflict. A conflict exists when an average consumer would likely be confused between the proposed mark and an existing one.

PROPOSED MARK: {proposed}
NICE CLASS: {nice_class}
EXISTING MARKS IN THIS CLASS:
{listing}

Reply ONLY with JSON:
{{"conflict": true|false, "offending": "<closest existing mark, or none>", "reasoning": "<short explanation>"}}"""
            raw = gl.nondet.exec_prompt(prompt, response_format="json")
            if not isinstance(raw, dict):
                try:
                    raw = json.loads(str(raw))
                except Exception:
                    raw = {}
            return json.dumps(normalize_check(raw))

        result = gl.eq_principle.prompt_comparative(
            do_check,
            principle="The boolean 'conflict' must be identical across validators; the offending mark named and the reasoning wording may differ.",
        )
        data = json.loads(result) if isinstance(result, str) else result
        if not validate_check(data):
            data = normalize_check(data if isinstance(data, dict) else {})
        return data

    # -------------------------------------------------------------- views
    @gl.public.view
    def get_mark(self, mark_id: str) -> dict:
        mark_id = str(mark_id)
        if mark_id not in self.marks:
            return {"exists": False}
        m = json.loads(self.marks[mark_id])
        m["exists"] = True
        return m

    @gl.public.view
    def stats(self) -> dict:
        return {
            "total_marks": int(self.mark_count),
            "checked": int(self.checked_count),
            "conflicts": int(self.conflict_count),
        }
