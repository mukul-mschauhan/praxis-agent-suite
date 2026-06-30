# Praxis Advisory
### A Claude-Skills-Driven Multi-Agent System for Consulting Engagements

This project is a working demo of an **agentic AI system built on Claude Skills**: a router
agent and four specialist agents whose behavior is defined entirely by editable `SKILL.md`
files, orchestrated by a lightweight Python state machine, protected by deterministic
guardrails, and graded by an independent evaluator agent — all surfaced through a live
decision trace in a web UI.

---

## 1. Problem Statement

Management consulting engagements typically require triangulating three lenses on the same
business problem — **market**, **financial**, and **risk** — before a recommendation is
client-ready. Doing this manually is slow, and doing it with a single undifferentiated LLM
prompt is unreliable: the model conflates lenses, invents numbers, glosses over risk, and
gives no audit trail for why it said what it said.

**Goal:** build a system that takes a raw client problem brief and produces a client-ready,
risk-aware recommendation by routing the work to the *right* specialist agents, refusing to
proceed on unethical/illegal asks, labelling every assumption instead of inventing facts, and
grading its own output before it's shown to the user — with every step visible and explainable
for a classroom audit.

---

## 2. System Design

### 2.1 Why "Claude Skills" instead of a single mega-prompt

Each agent's entire behavior — role, allowed scope, forbidden scope, required output schema —
lives in a plain Markdown file under `/skills/<agent_name>/SKILL.md`. That file **is** the
agent's system prompt. This means:

- A non-engineer (e.g. a consulting SME) can change agent behavior by editing markdown, with
  zero Python changes.
- Each skill explicitly states what it must **not** do, which is the primary lever used to stop
  scope creep (e.g. the Market Analysis agent is explicitly forbidden from giving ROI
  judgments).
- Skills are visible to the end user in the UI ("View Agent Skills" button) — the system is
  explainable, not a black box.

### 2.2 Architecture

```
                        ┌─────────────────┐
   Client Brief  ───►   │  Router Agent    │  (skill: router)
                        │  decides WHICH    │
                        │  specialists run  │
                        └──────┬───────────┘
                               │ selected_skills[]
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ┌────────────────┐┌────────────────┐┌────────────────┐
     │ Market Analysis ││ Financial      ││ Risk Assessment │
     │ Agent            ││ Analysis Agent ││ Agent (can      │
     │                  ││                ││ HARD-STOP)      │
     └────────┬─────────┘└───────┬────────┘└────────┬────────┘
              │  each output passes through          │
              │  deterministic GUARDRAILS             │
              └────────────────┬───────────────────────┘
                                ▼
                      ┌──────────────────────┐
                      │ Strategy Synthesis    │  (skill: strategy_synthesis)
                      │ Agent — combines all  │
                      │ specialist outputs    │
                      └──────────┬────────────┘
                                 ▼
                      ┌──────────────────────┐
                      │ Evaluation Agent       │  (skill: evaluation)
                      │ scores vs rubric;      │
                      │ PASS or REVISE         │
                      └──────────┬────────────┘
                                 │ if REVISE (max 1 retry)
                                 ▼
                  Strategy Synthesis re-run with evaluator feedback
                                 ▼
                         Final client report
```

Every box above is a single Claude API call whose system prompt is the corresponding
`SKILL.md`. The full request/response, latency, token counts, and guardrail verdict for every
box are recorded in `trace[]` and rendered live in the UI.

### 2.3 Agents (built with a lightweight custom orchestration framework)

This is intentionally **not** built on CrewAI/LangGraph — a from-scratch ~150-line
orchestrator (`core/orchestrator.py`) was used so that every routing decision, retry, and
guardrail check is fully transparent in plain Python for the classroom demo, with no framework
internals to explain away. The same skill files would drop into CrewAI almost unchanged (each
`SKILL.md` is just an agent's `backstory`/`goal` + a Pydantic-able output schema) if you want to
port it.

| Agent | Skill file | Responsibility | Can veto engagement? |
|---|---|---|---|
| Router | `skills/router/SKILL.md` | Decides which specialists are needed from the brief | No |
| Market Analysis | `skills/market_analysis/SKILL.md` | Competitive position, demand signals | No |
| Financial Analysis | `skills/financial_analysis/SKILL.md` | Cost structure, ROI judgment | No |
| Risk Assessment | `skills/risk_assessment/SKILL.md` | Regulatory/reputational/operational risk | **Yes — `hard_stop`** |
| Strategy Synthesis | `skills/strategy_synthesis/SKILL.md` | Combines everything into one report | No (must honor a hard stop) |
| Evaluation | `skills/evaluation/SKILL.md` | Independent QA scoring of the final report | No (triggers 1 revision pass) |

### 2.4 Guardrails (`core/guardrails.py`)

Guardrails are deliberately **deterministic, non-LLM checks** — fast, auditable, and immune to
prompt manipulation — run on every single agent output before it's allowed downstream:

- **PII detection** — regex screen for emails, SSN-like, card/account-like patterns. Blocks the
  pipeline if found.
- **Scope-violation detection** — flags an agent's output referencing fields that belong to a
  different agent's lane (e.g. Market Analysis output mentioning `roi_judgment`).
- **Unlabelled-numeric-claim warning** — flags (does not block) any specialist output with a
  percentage/number and no `"assumption"` marker anywhere in the JSON, surfacing possible
  hallucinated statistics for human review.
- **Hard-stop veto** — handled at the orchestration layer: if `risk_assessment` returns
  `hard_stop: true`, Strategy Synthesis is instructed it MUST decline/redirect, and the UI shows
  a red banner instead of a normal recommendation.

### 2.5 Evaluation of the agentic output

This is the part most demos skip: **the system grades its own final answer.** The Evaluation
agent receives only the original brief and the final synthesized report (it never sees the
specialist outputs, to keep it an honest "fresh eyes" reviewer) and scores it 1–5 on four axes:
`completeness`, `groundedness`, `actionability`, `risk_coverage`. If the average score is below
4.0, or any single axis is below 3, the verdict is `REVISE` and the orchestrator automatically
re-runs Strategy Synthesis once with the specific feedback attached, then re-evaluates. The UI
shows whichever pass is final, plus a "(after 1 revision)" tag so the audit trail is honest
about what happened.

### 2.6 Decision trace / explainability

Every stage's prompt, raw model output, parsed JSON, latency, token usage, and guardrail
verdict is captured in an ordered `trace[]` list returned by `/api/run` and rendered as an
expandable accordion in the UI — this is the literal mechanism for "showing how the decision
making happened" in a live classroom demo, with no extra logging infrastructure required.

---

## 3. Project Structure

```
praxis-agent-suite/
├── app.py                       # Flask backend: serves UI + /api/run + /api/skills
├── requirements.txt
├── core/
│   ├── claude_client.py         # Anthropic API wrapper (model, JSON extraction, usage/latency)
│   ├── skills_loader.py         # Reads SKILL.md files — these ARE the agents' system prompts
│   ├── guardrails.py            # Deterministic PII / scope / unlabelled-number checks
│   └── orchestrator.py          # The state machine: routing -> specialists -> synth -> eval -> revise
├── skills/
│   ├── router/SKILL.md
│   ├── market_analysis/SKILL.md
│   ├── financial_analysis/SKILL.md
│   ├── risk_assessment/SKILL.md
│   ├── strategy_synthesis/SKILL.md
│   └── evaluation/SKILL.md
├── templates/index.html         # Professional dark dashboard UI
└── static/{style.css, app.js}   # Pipeline visualization, trace accordion, report renderer
```

---

## 4. Running the Demo

```bash
git clone <this-repo>
cd praxis-agent-suite
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000**.

1. Paste your **Anthropic API key** into the input field (sent only with the request,
   never persisted to disk or logs — safe to demo in front of a class).
2. Paste a client problem brief, or click one of the three example chips.
3. Click **Run Engagement** and watch the pipeline panel populate live: which agents were
   invoked and why, each guardrail verdict, the full prompt/response trace, and the final
   evaluated report.
4. Click **View Agent Skills** at any time to show the class the actual `SKILL.md` files
   driving the agents — this is the cleanest way to demonstrate that behavior comes from the
   skill definitions, not hidden logic.

### Suggested demo briefs (also built into the UI as one-click chips)
- *Pricing & competition* — exercises Market Analysis + Financial Analysis.
- *Layoffs & change management* — exercises Risk Assessment heavily; can trip the hard-stop
  guardrail if framed as evading legal disclosure obligations.
- *Market entry* — exercises all three specialists plus a clean multi-revision-free pass.

---

## 5. Design Decisions & Trade-offs

- **Why JSON-structured outputs everywhere?** So every agent's output is independently
  guardrail-checkable and so Strategy Synthesis/Evaluation can programmatically consume prior
  agent outputs rather than re-parsing prose.
- **Why a custom orchestrator instead of CrewAI?** Full transparency for a live demo — no
  framework internals between "what the code does" and "what you can show the class." The
  skill-file pattern is framework-agnostic by design.
- **Why deterministic (non-LLM) guardrails?** Auditability and speed — they can't be talked out
  of doing their job by a clever prompt, and they don't burn extra Claude API calls/latency.
- **Why a single revision retry cap?** Bounds cost/latency for a live demo while still showing
  the self-correction loop end-to-end.

---

## 6. Security Notes

- The Anthropic API key is supplied client-side per request and is never written to disk,
  environment files, or server logs in this codebase.
- All PII-pattern guardrail hits block the pipeline rather than silently passing through.
