---
name: as-is-process-navigator
description: Builds a single interactive HTML navigator of an as-is process from a process document (SOP, workshop notes, interview notes, process map, pain-point list). It has two linked views. The structured view decomposes the process from L1 down to L5 (stage, step, activity, task) and shows roles, systems, execution mode, pain points, ideas captured, open questions, inputs and outputs. The flow view is a swimlane diagram with decision gates, loop-backs and output documents. Every item links between the two views, and role, system, search and pain/idea filters apply to both. Use when the user wants to navigate, review or present an as-is process, its pain points and improvement ideas, from any domain.
allowed-tools: run_skill_script read_wiki_page write_temp_file read_temp_file save_output_text save_output_file
---

# As-Is Process Navigator

Input: a document that describes a process (SOP, notes, process map, pain-point list). Output: one file, `process-navigator.html`.
You never write code. You write one JSON file (`model.json`), and a bundled script renders the HTML.

## Do not ask questions
Work from what you were given. Use these defaults and say which ones you used in the final message:
- Levels: stage = L2, step = L3, activity = L4, task = L5. L1 is the whole process (`meta.processName`).
- A level the document does not cover stays empty. Never invent L4/L5 detail to fill space. A step without activities is fine.
- Execution mode defaults to `manual` when the document does not say how the work is done.
- Role of an activity or task defaults to its parent's role (the script inherits it).
- No `flow` block: the script builds a simple left-to-right flow from the step order. Write a `flow` block only when the document shows swimlanes, hand-overs, decision gates or loops.
- Pain points get severity `medium` unless the document signals otherwise.

## Steps
1. **Read** the provided document(s) fully.
2. **Decompose** into stages, steps, activities and tasks (see "What goes where"). Capture roles, systems, pain points, ideas, open questions, inputs and outputs wherever the document states them.
3. **Write the input file**: author `model.json` in the format below and save it with `write_temp_file`.
4. **Run**: call `run_skill_script` with script `build_navigator.py`, `--input model.json`, `--output process-navigator.html`.
   - The script validates first. On failure it lists every problem on stderr. Fix the JSON, save it again and re-run until it prints PASS.
5. **Deliver**: save `process-navigator.html` with `save_output_file`, then reply with a short summary: counts per level, number of pain points, ideas and open questions, the defaults you used, and anything in the document that was ambiguous.

## What goes where
| Level | JSON | Meaning |
|---|---|---|
| L1 | `meta` | the whole process |
| L2 | `stages[]` | phase or major step; shown as a band in the flow |
| L3 | `stages[].steps[]` | the unit drawn as a box in the flow view and placed in a swimlane |
| L4 | `steps[].activities[]` | what is done inside a step |
| L5 | `activities[].tasks[]` | the lowest-level action |

- Pain points, ideas and questions attach to the item they belong to. The views roll counts up to the parent, so do not repeat them on parents.
- A **decision** is a gate where someone chooses between outcomes (go, loop back, pause, stop, hand off). Put it in `decisions[]` and place it in the flow.
- An **idea** is an improvement already captured in the document (automation, AI assist, process change). Do not add your own.
- A **pain point** is a stated problem, delay, workaround or risk. Quote or paraphrase the document.

## model.json format
Required: `meta.title`, `roles[]` (id, name), `stages[]` (at least one, each with at least one step). Everything else is optional.
Ids: letters, digits, `_`, `.`, `-`. Every id must be unique across the whole file, including roles, systems, decisions and flow nodes.

```json
{
  "meta": {
    "title": "Page title",
    "subtitle": "Shown under the title",
    "processName": "Name of the L1 process",
    "eyebrow": "As-is process",
    "description": "Two or three sentences for the overview page.",
    "note": "Optional banner, for example 'Illustrative data'."
  },
  "roles": [{ "id": "ops", "name": "Operations team", "short": "Ops", "color": "#0052cc" }],
  "systems": [{ "id": "erp", "name": "ERP" }],
  "decisions": [
    {
      "id": "d-gate",
      "name": "Release gate",
      "owner": "ops",
      "after": "st-1",
      "question": "Is the output good enough to release?",
      "criteria": ["Checklist complete"],
      "options": [
        { "label": "Release", "kind": "forward" },
        { "label": "Rework", "kind": "loop", "to": "step-a" },
        { "label": "Pause", "kind": "pause" },
        { "label": "Stop", "kind": "stop" }
      ],
      "painPoints": [], "ideas": [], "questions": [], "systems": []
    }
  ],
  "stages": [
    {
      "id": "st-1", "code": "Stage 1", "name": "Stage name", "role": "ops",
      "purpose": "One sentence.", "outputs": ["Deliverable"],
      "steps": [
        {
          "id": "step-a", "code": "1.1", "name": "Step name",
          "role": "ops", "supportRoles": [], "mode": "manual", "duration": "2 days",
          "interface": false,
          "description": "What happens.",
          "systems": ["erp"],
          "inputs": ["Request"], "outputs": ["Checked request"],
          "painPoints": [{ "text": "Stated problem.", "severity": "high" }],
          "ideas": [{ "title": "Idea title", "text": "Detail.", "type": "Automation" }],
          "questions": ["Open question from the document?"],
          "activities": [
            {
              "id": "act-a1", "name": "Activity name", "mode": "system", "systems": ["erp"],
              "tasks": [{ "id": "t-a1-1", "name": "Task name", "painPoints": ["A plain string also works."] }]
            }
          ]
        }
      ]
    }
  ],
  "flow": {
    "lanes": ["ops"],
    "nodes": [
      { "kind": "start", "id": "start", "label": "Request received", "lane": "ops", "band": "Entry", "outputs": ["Request"] },
      { "kind": "step", "ref": "step-a" },
      { "kind": "decision", "ref": "d-gate" },
      { "kind": "end", "id": "end", "label": "Done", "lane": "ops", "band": "Exit" }
    ]
  }
}
```

### Field rules
- `role`: id from `roles`. Stages and steps must have one. Activities and tasks inherit the parent's role when omitted.
- `supportRoles`: ids of other roles that take part. They count toward the role filter and the role matrix.
- `mode`: `manual`, `system` (supported by a tool) or `automated`. Activities and tasks inherit the parent's mode when omitted. Default `manual`.
- `interface: true` marks a step that crosses an organisational boundary (shown pink in the flow).
- `painPoints[]`: a string, or `{ "text", "severity": "low|medium|high" }`.
- `ideas[]`: a string, or `{ "title", "text", "type" }`. `type` is free text such as AI, Automation, Process, Data.
- `systems[]`: ids from the top-level `systems`. Declare every system once.
- `inputs[]` / `outputs[]`: strings, or `{ "label" }`. Outputs on a step in the flow are drawn as document icons.
- `decisions[].before` / `after`: a **stage** id that the gate sits in front of or behind. At least one is required.
- Decision option `kind`: `forward` (continue to the next node), `fast` (skip ahead), `loop` (return), `stop`, `pause`, `handoff`. `fast` and `loop` need `to` (a step id or a flow node id). `stop`, `pause` and `handoff` end the flow with a terminal circle.
- `flow.nodes[]` kinds: `step` (`ref` = an L3 id), `decision` (`ref` = a decision id), `start` and `end` (need `id`, `label`; optional `lane`, `band`, `outputs`). Nodes are laid out left to right in the order written. Every L3 step must appear exactly once. Optional `next: [ids]` overrides the default "next node" link.
- `flow.lanes[]`: role ids, top to bottom. Omit to derive them from the roles used.

## Rules
- Use the document's wording for names. Do not translate or rename.
- Never fabricate pain points, ideas, systems, roles or durations. Omit what the document does not state.
- Keep names short (a box in the flow shows about 4 lines of 19 characters). Put detail in `description`.
- Prefer 3 to 7 stages, and no more than about 8 steps per stage, so the flow stays readable.
- If the document contains several unrelated processes, build one model for the main one and say what was left out.
- If you invent sample data because the user asked for a demo, set `meta.note` to say it is illustrative.
