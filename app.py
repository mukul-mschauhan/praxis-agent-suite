"""
app.py
Flask backend serving the frontend and the /api/run endpoint that executes
the full Claude-Skills multi-agent pipeline. The Anthropic API key is
supplied per-request by the user in the browser (never stored server-side,
never logged to disk) so this is safe to demo from a shared repo.
"""
from flask import Flask, request, jsonify, render_template
from core.orchestrator import Orchestrator
from core.skills_loader import list_skills, load_skill

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/skills", methods=["GET"])
def get_skills():
    """Lets the frontend display the actual SKILL.md contents driving each agent."""
    skills = {}
    for name in list_skills():
        skills[name] = load_skill(name)
    return jsonify(skills)


@app.route("/api/run", methods=["POST"])
def run_engagement():
    data = request.get_json(force=True)
    api_key = (data.get("api_key") or "").strip()
    brief = (data.get("brief") or "").strip()

    if not api_key:
        return jsonify({"error": "Anthropic API key is required."}), 400
    if not brief or len(brief) < 10:
        return jsonify({"error": "Please provide a more detailed client problem brief."}), 400

    try:
        orchestrator = Orchestrator(api_key)
        result = orchestrator.run(brief)
        return jsonify(result)
    except Exception as exc:  # surfaced directly to the demo UI for transparency
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
