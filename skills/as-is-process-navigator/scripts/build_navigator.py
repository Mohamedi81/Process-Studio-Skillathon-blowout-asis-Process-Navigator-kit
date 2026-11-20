#!/usr/bin/env python3
"""Render an as-is process model (JSON) into one self-contained HTML navigator.

The HTML has two linked views: a structured L1-L5 view and a swimlane flow view.
No domain content lives here: the model comes from --input, the layout from
../assets/navigator-template.html.

Usage: python3 build_navigator.py --input model.json --output process-navigator.html
Exit 0: output written. Exit 1: every problem printed to stderr, one per line.
Standard library only.
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_OUTPUT_NAME = "process-navigator.html"
PLACEHOLDER = "__MODEL_JSON__"
ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.\-]*"
MODES = ("manual", "system", "automated")
SEVERITIES = ("low", "medium", "high")
OPTION_KINDS = ("forward", "fast", "loop", "stop", "pause", "handoff")
NEEDS_TARGET = ("fast", "loop")
NODE_KINDS = ("step", "decision", "start", "end")
LEVEL_NAMES = {2: "stage", 3: "step", 4: "activity", 5: "task"}
CHILD_KEY = {2: "steps", 3: "activities", 4: "tasks"}


class Problems:
    def __init__(self):
        self.items = []

    def add(self, where, msg):
        self.items.append(f"{where}: {msg}")


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def is_text(value):
    return isinstance(value, str) and value.strip() != ""


def text_of(entry, keys):
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        for key in keys:
            if is_text(entry.get(key)):
                return entry[key]
    return ""


def check_id(value, where, seen, problems):
    if not is_text(value):
        problems.add(where, "missing 'id'")
        return
    if re.fullmatch(ID_PATTERN, value) is None:
        problems.add(where, f"id '{value}' may only contain letters, digits, '_', '.', '-' and must start with a letter or digit")
    if value in seen:
        problems.add(where, f"duplicate id '{value}' (used more than once; every id must be unique across the whole model, including roles and systems)")
    else:
        seen[value] = where


def check_annotations(item, where, system_ids, problems):
    for i, p in enumerate(as_list(item.get("painPoints"))):
        if not text_of(p, ("text",)):
            problems.add(f"{where}.painPoints[{i}]", "needs text (a string, or an object with 'text')")
        if isinstance(p, dict) and p.get("severity") not in (None, *SEVERITIES):
            problems.add(f"{where}.painPoints[{i}]", f"severity '{p.get('severity')}' must be one of {', '.join(SEVERITIES)}")
    for i, idea in enumerate(as_list(item.get("ideas"))):
        if not text_of(idea, ("title", "text")):
            problems.add(f"{where}.ideas[{i}]", "needs a title (a string, or an object with 'title')")
    for i, q in enumerate(as_list(item.get("questions"))):
        if not is_text(q):
            problems.add(f"{where}.questions[{i}]", "must be a non-empty string")
    for s in as_list(item.get("systems")):
        if s not in system_ids:
            problems.add(where, f"unknown system '{s}' (declare it in 'systems')")
    for key in ("inputs", "outputs"):
        for i, entry in enumerate(as_list(item.get(key))):
            if not text_of(entry, ("label",)):
                problems.add(f"{where}.{key}[{i}]", "must be a string or an object with 'label'")


def walk(item, level, parent, ctx):
    """Validate one item and its children; fill role and mode from the parent when absent."""
    problems, seen, role_ids, system_ids = ctx["problems"], ctx["seen"], ctx["roles"], ctx["systems"]
    if not isinstance(item, dict):
        problems.add(LEVEL_NAMES[level], "must be an object")
        return
    where = f"{LEVEL_NAMES[level]} '{item.get('id', '?')}'"
    check_id(item.get("id"), where, seen, problems)
    if not is_text(item.get("name")):
        problems.add(where, "missing 'name'")
    inherited_role = False
    if not item.get("role") and parent is not None and parent.get("role"):
        item["role"] = parent["role"]
        inherited_role = True
    if not item.get("role"):
        if parent is None or not parent.get("role"):
            problems.add(where, "missing 'role' (stages and steps must name a role)" if level <= 3 else "missing 'role' and no parent role to inherit")
    elif not inherited_role and item["role"] not in role_ids:
        problems.add(where, f"unknown role '{item['role']}' (declare it in 'roles')")
    for r in as_list(item.get("supportRoles")):
        if r not in role_ids:
            problems.add(where, f"unknown supportRole '{r}'")
    if level >= 3:
        if not item.get("mode"):
            parent_mode = parent.get("mode") if parent and level > 3 else None
            item["mode"] = parent_mode if parent_mode in MODES else "manual"
        elif item["mode"] not in MODES:
            problems.add(where, f"mode '{item['mode']}' must be one of {', '.join(MODES)}")
    check_annotations(item, where, system_ids, problems)
    key = CHILD_KEY.get(level)
    if key:
        children = item.get(key)
        if level == 2 and not as_list(children):
            problems.add(where, "needs at least one step in 'steps'")
        for child in as_list(children):
            if not isinstance(child, dict):
                problems.add(where, f"every entry of '{key}' must be an object")
                continue
            ctx["registry"][child.get("id")] = (level + 1, child)
            walk(child, level + 1, item, ctx)


def validate(model):
    """Return (problems, model). The model is normalised in place."""
    p = Problems()
    if not isinstance(model, dict):
        p.add("model", "top level must be a JSON object")
        return p.items, model
    meta = model.setdefault("meta", {})
    if not is_text(meta.get("title")):
        p.add("meta", "missing 'title'")

    seen, registry = {}, {}
    role_ids, system_ids = set(), set()
    for i, r in enumerate(as_list(model.get("roles"))):
        where = f"roles[{i}]"
        if not isinstance(r, dict) or not is_text(r.get("name")):
            p.add(where, "needs an object with 'id' and 'name'")
            continue
        check_id(r.get("id"), where, seen, p)
        role_ids.add(r.get("id"))
    if not role_ids:
        p.add("roles", "declare at least one role")
    for i, s in enumerate(as_list(model.get("systems"))):
        where = f"systems[{i}]"
        if not isinstance(s, dict) or not is_text(s.get("name")):
            p.add(where, "needs an object with 'id' and 'name'")
            continue
        check_id(s.get("id"), where, seen, p)
        system_ids.add(s.get("id"))

    stages = as_list(model.get("stages"))
    if not stages:
        p.add("stages", "declare at least one stage")
    ctx = {"problems": p, "seen": seen, "roles": role_ids, "systems": system_ids, "registry": registry}
    for st in stages:
        if not isinstance(st, dict):
            p.add("stages", "every stage must be an object")
            continue
        registry[st.get("id")] = (2, st)
        walk(st, 2, None, ctx)

    step_ids = {k for k, (lvl, _) in registry.items() if lvl == 3}
    stage_ids = {k for k, (lvl, _) in registry.items() if lvl == 2}

    # decisions
    decisions = as_list(model.get("decisions"))
    decision_ids = set()
    for i, d in enumerate(decisions):
        where = f"decision '{d.get('id', i) if isinstance(d, dict) else i}'"
        if not isinstance(d, dict):
            p.add(where, "must be an object")
            continue
        check_id(d.get("id"), where, seen, p)
        decision_ids.add(d.get("id"))
        if not is_text(d.get("name")):
            p.add(where, "missing 'name'")
        if d.get("owner") not in role_ids:
            p.add(where, f"owner '{d.get('owner')}' is not a declared role")
        if not d.get("before") and not d.get("after"):
            p.add(where, "needs 'before' or 'after' naming a stage id")
        for key in ("before", "after"):
            if d.get(key) and d[key] not in stage_ids:
                p.add(where, f"'{key}' must be a stage id, got '{d[key]}'")
        options = as_list(d.get("options"))
        if not options:
            p.add(where, "needs at least one option")
        for j, o in enumerate(options):
            if not isinstance(o, dict) or not is_text(o.get("label")):
                p.add(where, f"options[{j}] needs a 'label'")
                continue
            o.setdefault("kind", "forward")
            if o["kind"] not in OPTION_KINDS:
                p.add(where, f"options[{j}] kind '{o['kind']}' must be one of {', '.join(OPTION_KINDS)}")
            if o["kind"] in NEEDS_TARGET and not o.get("to"):
                p.add(where, f"options[{j}] ('{o['label']}', kind {o['kind']}) needs 'to' naming the step or node it returns to")
        check_annotations(d, where, system_ids, p)

    # flow
    flow = model.get("flow")
    if not isinstance(flow, dict) or not as_list(flow.get("nodes")):
        model["flow"] = flow = auto_flow(model, registry, decisions)
    node_ids = set()
    lanes = as_list(flow.get("lanes"))
    for ln in lanes:
        if ln not in role_ids:
            p.add("flow.lanes", f"lane '{ln}' is not a declared role")
    placed_steps = set()
    for i, n in enumerate(as_list(flow.get("nodes"))):
        where = f"flow.nodes[{i}]"
        if not isinstance(n, dict):
            p.add(where, "must be an object")
            continue
        kind = n.get("kind", "step")
        n["kind"] = kind
        if kind not in NODE_KINDS:
            p.add(where, f"kind '{kind}' must be one of {', '.join(NODE_KINDS)}")
        elif kind == "step":
            if n.get("ref") not in step_ids:
                p.add(where, f"ref '{n.get('ref')}' is not a step (L3) id")
            else:
                placed_steps.add(n["ref"])
                node_ids.add(n["ref"])
        elif kind == "decision":
            if n.get("ref") not in decision_ids:
                p.add(where, f"ref '{n.get('ref')}' is not a decision id")
            else:
                node_ids.add(n["ref"])
        else:
            check_id(n.get("id"), where, seen, p)
            node_ids.add(n.get("id"))
            if not is_text(n.get("label")):
                p.add(where, f"{kind} node needs a 'label'")
        if n.get("lane") and n["lane"] not in role_ids:
            p.add(where, f"lane '{n['lane']}' is not a declared role")
        for ref in as_list(n.get("next")):
            n.setdefault("_next_check", []).append(ref)
    for n in as_list(flow.get("nodes")):
        for ref in n.pop("_next_check", []):
            if ref not in node_ids:
                p.add("flow", f"node next '{ref}' is not a node in the flow")
    for d in decisions:
        if isinstance(d, dict):
            for o in as_list(d.get("options")):
                if isinstance(o, dict) and o.get("to") and o["to"] not in node_ids:
                    p.add(f"decision '{d.get('id')}'", f"option '{o.get('label')}' targets '{o['to']}', which is not a node in the flow")
    for sid in sorted(step_ids - placed_steps):
        p.add("flow", f"step '{sid}' is not placed in the flow (add a step node, or remove 'flow' to auto-generate it)")
    used = [n.get("lane") or (registry[n["ref"]][1].get("role") if n.get("kind") == "step" and n.get("ref") in registry else None) for n in as_list(flow.get("nodes"))]
    if not lanes:
        flow["lanes"] = [r for r in dict.fromkeys(u for u in used if u)] or sorted(role_ids)
    return p.items, model


def auto_flow(model, registry, decisions):
    """Sequential flow: steps in order, decisions placed before/after their stage."""
    nodes = []
    placed = set()
    for st in as_list(model.get("stages")):
        if not isinstance(st, dict):
            continue
        for d in decisions:
            if isinstance(d, dict) and d.get("before") == st.get("id") and d.get("id") not in placed:
                nodes.append({"kind": "decision", "ref": d["id"]})
                placed.add(d["id"])
        for step in as_list(st.get("steps")):
            if isinstance(step, dict):
                nodes.append({"kind": "step", "ref": step.get("id")})
        for d in decisions:
            if isinstance(d, dict) and d.get("after") == st.get("id") and d.get("id") not in placed:
                nodes.append({"kind": "decision", "ref": d["id"]})
                placed.add(d["id"])
    return {"lanes": [], "nodes": nodes}


def render(model, template):
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return template.replace(PLACEHOLDER, payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    try:
        model = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FAIL: input is not readable JSON: {exc}", file=sys.stderr)
        return 1

    problems, model = validate(model)
    if problems:
        print(f"FAIL: {len(problems)} issue(s)", file=sys.stderr)
        for line in problems:
            print(f" - {line}", file=sys.stderr)
        return 1

    template_path = Path(__file__).resolve().parent.parent / "assets" / "navigator-template.html"
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL: cannot read template {template_path}: {exc}", file=sys.stderr)
        return 1
    if PLACEHOLDER not in template:
        print(f"FAIL: template is missing the {PLACEHOLDER} placeholder", file=sys.stderr)
        return 1

    Path(args.output).write_text(render(model, template), encoding="utf-8")
    print(f"PASS: wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
