"""
core/orchestrator.py
The orchestrator is the "brain" that decides which Claude-Skill-driven agent
runs when. It is intentionally a thin, explainable state machine rather than
a black box, because the whole point of this project is to be able to show
the trace of WHY each agent ran, in the classroom demo.

Pipeline:
  1. Router agent (skill: router)            -> decides which specialists to invoke
  2. Specialist agents (subset of 3)          -> each wrapped with guardrails
  3. Hard-stop check                          -> risk_assessment can veto the engagement
  4. Strategy synthesis agent                 -> combines specialist outputs
  5. Evaluation agent                         -> grades the synthesis against a rubric
  6. If verdict == REVISE (max 1 retry)       -> re-run synthesis with evaluator feedback
"""
import datetime
from core.claude_client import ClaudeClient
from core.skills_loader import load_skill
from core import guardrails

SPECIALIST_SKILLS = ["market_analysis", "financial_analysis", "risk_assessment"]


class Orchestrator:
    def __init__(self, api_key: str):
        self.claude = ClaudeClient(api_key)
        self.trace = []

    def _log(self, step: str, detail: dict):
        self.trace.append({
            "step": step,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            **detail,
        })

    def _run_agent(self, skill_name: str, user_prompt: str) -> dict:
        system_prompt = load_skill(skill_name)
        result = self.claude.call(system_prompt, user_prompt)
        guard_result = guardrails.run_guardrails(skill_name, result["raw_text"], result["parsed"])
        self._log(f"agent:{skill_name}", {
            "input_prompt": user_prompt,
            "output_raw": result["raw_text"],
            "output_parsed": result["parsed"],
            "latency_seconds": result["latency_seconds"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "guardrails": guard_result,
        })
        return {"result": result, "guardrails": guard_result}

    def run(self, client_brief: str) -> dict:
        # ---------- STAGE 1: ROUTING ----------
        router_prompt = (
            f"Client problem brief:\n\"\"\"\n{client_brief}\n\"\"\"\n\n"
            "Decide which specialist skills to invoke per your instructions."
        )
        router_out = self._run_agent("router", router_prompt)
        router_parsed = router_out["result"]["parsed"] or {}
        selected = router_parsed.get("selected_skills") or SPECIALIST_SKILLS
        selected = [s for s in selected if s in SPECIALIST_SKILLS] or SPECIALIST_SKILLS

        # ---------- STAGE 2: SPECIALISTS ----------
        specialist_outputs = {}
        hard_stop_triggered = False
        hard_stop_reason = ""
        for skill_name in selected:
            spec_prompt = (
                f"Client problem brief:\n\"\"\"\n{client_brief}\n\"\"\"\n\n"
                "Produce your specialist analysis per your skill instructions."
            )
            out = self._run_agent(skill_name, spec_prompt)
            parsed = out["result"]["parsed"]
            specialist_outputs[skill_name] = parsed
            if skill_name == "risk_assessment" and parsed and parsed.get("hard_stop"):
                hard_stop_triggered = True
                hard_stop_reason = parsed.get("hard_stop_reason", "Unspecified hard stop.")

        # ---------- STAGE 3: SYNTHESIS ----------
        synthesis_prompt = (
            f"Client problem brief:\n\"\"\"\n{client_brief}\n\"\"\"\n\n"
            f"Specialist outputs (JSON):\n{specialist_outputs}\n\n"
            f"hard_stop_triggered: {hard_stop_triggered}, reason: {hard_stop_reason}\n\n"
            "Produce the synthesized client-ready recommendation per your skill instructions. "
            "If hard_stop_triggered is true, your output MUST set decline_or_redirect true."
        )
        synth_out = self._run_agent("strategy_synthesis", synthesis_prompt)
        synthesis_result = synth_out["result"]["parsed"]

        # ---------- STAGE 4: EVALUATION ----------
        eval_prompt = (
            f"Client problem brief:\n\"\"\"\n{client_brief}\n\"\"\"\n\n"
            f"Final synthesized report (JSON):\n{synthesis_result}\n\n"
            "Score this per your rubric."
        )
        eval_out = self._run_agent("evaluation", eval_prompt)
        evaluation_result = eval_out["result"]["parsed"]

        # ---------- STAGE 5: ONE REVISION PASS IF NEEDED ----------
        revised = False
        if evaluation_result and evaluation_result.get("verdict") == "REVISE":
            revised = True
            revision_prompt = (
                f"Client problem brief:\n\"\"\"\n{client_brief}\n\"\"\"\n\n"
                f"Specialist outputs (JSON):\n{specialist_outputs}\n\n"
                f"Your previous synthesis (JSON):\n{synthesis_result}\n\n"
                f"Evaluator feedback you MUST address:\n{evaluation_result.get('feedback')}\n\n"
                "Produce a revised synthesized recommendation per your skill instructions, "
                "directly addressing every piece of feedback."
            )
            synth_out2 = self._run_agent("strategy_synthesis", revision_prompt)
            synthesis_result = synth_out2["result"]["parsed"]

            eval_prompt2 = (
                f"Client problem brief:\n\"\"\"\n{client_brief}\n\"\"\"\n\n"
                f"Revised final synthesized report (JSON):\n{synthesis_result}\n\n"
                "Score this per your rubric."
            )
            eval_out2 = self._run_agent("evaluation", eval_prompt2)
            evaluation_result = eval_out2["result"]["parsed"]

        return {
            "client_brief": client_brief,
            "router_decision": router_parsed,
            "selected_skills": selected,
            "specialist_outputs": specialist_outputs,
            "hard_stop_triggered": hard_stop_triggered,
            "hard_stop_reason": hard_stop_reason,
            "final_report": synthesis_result,
            "evaluation": evaluation_result,
            "revision_occurred": revised,
            "trace": self.trace,
        }
