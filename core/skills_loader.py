"""
core/skills_loader.py
Loads each agent's SKILL.md from disk. The SKILL.md content IS the system
prompt for that agent — this is the literal mechanism by which "Claude Skills"
drive agent behavior in this project: editing a markdown file changes agent
behavior with zero Python code changes.
"""
import os

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")


def load_skill(skill_name: str) -> str:
    path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Skill '{skill_name}' not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def list_skills() -> list:
    return [
        name for name in os.listdir(SKILLS_DIR)
        if os.path.isdir(os.path.join(SKILLS_DIR, name))
    ]
