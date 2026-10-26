"""State proposals and an observation-grounded, non-evolvable commit kernel."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import re
from .protocol import ProtocolError, exact_keys, string, string_list


def verifier_digest(verification: dict) -> str:
    import json
    return sha256(json.dumps(verification, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_verification(value: dict) -> dict:
    exact_keys(value, {"command", "contains"}, "verification")
    string(value["command"], "verification command", limit=8000)
    string_list(value["contains"], "verification contains")
    if value["command"].strip() in {"true", ":", "exit 0", "echo done", "echo success"}:
        raise ProtocolError("Use a substantive task check, not an unconditional success command")
    return deepcopy(value)


def new_goal(value: dict) -> dict:
    exact_keys(value, {"id", "description", "verification"}, "new goal")
    gid = string(value["id"], "goal id", limit=80)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", gid):
        raise ProtocolError("Goal id must be a simple identifier")
    return {"id": gid, "description": string(value["description"], "goal description", limit=3000),
            "verification": validate_verification(value["verification"]), "status": "pending",
            "evidence_ids": [], "blocker": ""}


def initialize(value: dict, max_goals: int) -> list[dict]:
    exact_keys(value, {"goals"}, "initial state")
    if not isinstance(value["goals"], list) or not 1 <= len(value["goals"]) <= max_goals:
        raise ProtocolError("Initial goals must be a nonempty list within W.max_goals")
    result = [new_goal(g) for g in value["goals"]]
    if len({g["id"] for g in result}) != len(result):
        raise ProtocolError("Duplicate goal id")
    return result


def apply_proposal(state: list[dict], proposal: dict, receipts: dict[str, dict],
                   revision: int, memory: dict) -> tuple[list[dict], list[dict]]:
    """Validate first, then commit only supported transitions; input is untouched.

    Verification receipts are created by the harness after running a pre-bound
    public check. The model cannot supply receipt attributes or change old ones.
    Exit zero validates that check only; official task correctness stays unknown.
    """
    exact_keys(proposal, {"updates", "new_goals", "revised_verifications"}, "state proposal")
    if not all(isinstance(proposal[x], list) for x in proposal):
        raise ProtocolError("Proposal members must be arrays")
    result = deepcopy(state)
    by_id = {g["id"]: g for g in result}
    for entry in proposal["new_goals"]:
        goal = new_goal(entry)
        if goal["id"] in by_id:
            raise ProtocolError("Cannot replace an existing goal")
        result.append(goal)
        by_id[goal["id"]] = goal
    if len(result) > memory["W"]["max_goals"]:
        raise ProtocolError("Too many goals")
    revised = set()
    for entry in proposal["revised_verifications"]:
        exact_keys(entry, {"goal_id", "verification"}, "revised verification")
        gid = entry["goal_id"]
        if not isinstance(gid, str) or gid not in by_id or gid in revised:
            raise ProtocolError("Unknown/duplicate revised goal")
        revised.add(gid)
        goal = by_id[gid]
        goal.update(verification=validate_verification(entry["verification"]), status="pending", evidence_ids=[], blocker="")
    decisions = []
    seen = set()
    for update in proposal["updates"]:
        exact_keys(update, {"goal_id", "status", "evidence_ids", "blocker"}, "goal update")
        gid = update["goal_id"]
        if not isinstance(gid, str) or gid not in by_id or gid in seen:
            raise ProtocolError("Unknown/duplicate update goal")
        seen.add(gid)
        if update["status"] not in {"pending", "done", "blocked"}:
            raise ProtocolError("Invalid goal status")
        ids = string_list(update["evidence_ids"], "evidence ids")
        string(update["blocker"], "blocker", empty=True)
        goal = by_id[gid]
        accepted, reason = True, "non-completion proposal"
        if update["status"] == "done":
            accepted, reason = False, "No matching current successful verification receipt"
            for rid in ids:
                receipt = receipts.get(rid, {})
                if (gid not in revised and receipt.get("kind") == "verification"
                    and receipt.get("goal_id") == gid and receipt.get("revision") == revision
                    and receipt.get("verification_digest") == verifier_digest(goal["verification"])
                    and receipt.get("completed") is True and type(receipt.get("exit_code")) is int
                    and receipt["exit_code"] == 0 and receipt.get("synthetic") is False):
                    output = receipt["output"]
                    required = goal["verification"]["contains"] + memory["C"]["required_output"]
                    forbidden = memory["C"]["forbidden_output"]
                    if all(part in output for part in required) and not any(part in output for part in forbidden):
                        accepted, reason = True, f"Supported by actual public check receipt {rid}"
                        ids = [rid]
                        break
            if accepted and update["blocker"]:
                raise ProtocolError("A done goal cannot also have a blocker")
        elif any(rid not in receipts for rid in ids):
            accepted, reason = False, "Unknown evidence id"
        if update["status"] == "blocked" and not update["blocker"].strip():
            raise ProtocolError("Blocked status needs a concrete blocker")
        if accepted:
            goal.update(status=update["status"], evidence_ids=ids, blocker=update["blocker"])
        decisions.append({"goal_id": gid, "requested_status": update["status"], "accepted": accepted, "reason": reason})
    return result, decisions


def invalidate_completions(state: list[dict]) -> list[dict]:
    """Arbitrary terminal input may mutate artifacts: recheck before completion."""
    result = deepcopy(state)
    for goal in result:
        if goal["status"] == "done":
            goal.update(status="pending", evidence_ids=[], blocker="Environment changed after verification; recheck")
    return result
