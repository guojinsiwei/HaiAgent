"""JSON representation of the paper's bounded M=(E,W,rho,C) patch space.

Packages contain data only. No package can import code or replace the kernel.
This portable representation is an adapter choice, not upstream's YAML schema.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
import json
from pathlib import Path
import re

from .protocol import ProtocolError, exact_keys, string, string_list

COMPONENTS = ("E", "W", "rho", "C")


def validate_memory(memory: dict) -> dict:
    exact_keys(memory, {"schema_version", *COMPONENTS}, "Skill Memory")
    if type(memory["schema_version"]) is not int or memory["schema_version"] != 1:
        raise ProtocolError("Unsupported memory schema_version")
    if not isinstance(memory["E"], list) or len(memory["E"]) > 64:
        raise ProtocolError("E must contain at most 64 skills")
    ids = set()
    for skill in memory["E"]:
        exact_keys(skill, {"id", "description", "content", "tags"}, "skill")
        sid = string(skill["id"], "skill id", limit=80)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sid) or sid in ids:
            raise ProtocolError("Skill ids must be unique simple identifiers")
        ids.add(sid)
        string(skill["description"], "skill description", limit=2000)
        string(skill["content"], "skill content", limit=12000)
        string_list(skill["tags"], "skill tags")
    exact_keys(memory["W"], {"init_guidance", "update_guidance", "max_goals"}, "W")
    string(memory["W"]["init_guidance"], "init_guidance")
    string(memory["W"]["update_guidance"], "update_guidance")
    if type(memory["W"]["max_goals"]) is not int or not 1 <= memory["W"]["max_goals"] <= 32:
        raise ProtocolError("W.max_goals must be in [1,32]")
    exact_keys(memory["rho"], {"trigger", "retrieval", "max_skills"}, "rho")
    if memory["rho"]["trigger"] not in {"first_turn", "every_turn", "on_unresolved_change", "on_blocked"}:
        raise ProtocolError("Unsupported boundary trigger")
    if memory["rho"]["retrieval"] not in {"all", "lexical"}:
        raise ProtocolError("retrieval must be all or lexical")
    if type(memory["rho"]["max_skills"]) is not int or not 1 <= memory["rho"]["max_skills"] <= 64:
        raise ProtocolError("rho.max_skills must be in [1,64]")
    exact_keys(memory["C"], {"required_output", "forbidden_output"}, "C")
    string_list(memory["C"]["required_output"], "required_output")
    string_list(memory["C"]["forbidden_output"], "forbidden_output")
    if len(json.dumps(memory, ensure_ascii=False)) > 90000:
        raise ProtocolError("Skill Memory exceeds 90000 characters")
    return deepcopy(memory)


def memory_digest(memory: dict) -> str:
    clean = validate_memory(memory)
    return sha256(json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_memory(path: str | Path | None = None) -> dict:
    source = Path(path).read_text(encoding="utf-8") if path else files("recuris").joinpath("skills/neutral.json").read_text(encoding="utf-8")
    from .protocol import parse_object
    return validate_memory(parse_object(source))


def load_seed(profile: str = "neutral") -> dict:
    if profile not in {"neutral", "terminal"}:
        raise ValueError("seed profile must be neutral or terminal")
    name = "neutral.json" if profile == "neutral" else "terminal_seed.json"
    from .protocol import parse_object
    return validate_memory(parse_object(files("recuris").joinpath("skills/" + name).read_text(encoding="utf-8")))


def save_memory(memory: dict, path: str | Path) -> Path:
    clean = validate_memory(memory)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def invoke(memory: dict, state: list[dict], step: int, previous_unresolved: str | None) -> list[dict]:
    policy = memory["rho"]
    unresolved = [g for g in state if g["status"] != "done"]
    signature = unresolved_signature(state)
    fire = {
        "first_turn": step == 1,
        "every_turn": True,
        "on_unresolved_change": signature != previous_unresolved,
        "on_blocked": any(g["status"] == "blocked" for g in state),
    }[policy["trigger"]]
    if not fire:
        return []
    entries = memory["E"]
    if policy["retrieval"] == "lexical":
        # Deliberately conditions on unresolved state, never on the chat history.
        words = set(re.findall(r"\w+", " ".join(g["description"] for g in unresolved).lower()))
        def score(skill):
            skill_words = set(re.findall(r"\w+", (skill["description"] + " " + " ".join(skill["tags"])).lower()))
            return len(words & skill_words)
        entries = [s for s in sorted(entries, key=lambda s: (-score(s), s["id"])) if score(s) > 0]
    return deepcopy(entries[:policy["max_skills"]])


def unresolved_signature(state: list[dict]) -> str:
    return json.dumps([(g["id"], g["description"], g["status"], g.get("blocker"))
                       for g in state if g["status"] != "done"], ensure_ascii=False)
