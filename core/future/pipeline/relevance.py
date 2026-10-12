"""Role relevance by title for the job track (ST S02.02, revised after the live
audit of 2026-10-12, which showed a broad 'technical title' rule passed
recruiters, compliance analysts, economists and support roles).

Three outcomes:
  relevant    → ML / AI / research / software roles Pranav targets
  borderline  → technical but off-centre (SRE, security, architect, analyst…) → Evaluator decides
  irrelevant  → non-target function → fail
"""
from __future__ import annotations

import re

# Strong signals override a non-target keyword elsewhere in the title
# ("Research Engineer, Chip Design RL" is a research role, not chip design).
STRONG = re.compile(r"machine learning|\bml\b|\bllm|deep learning|computer vision|\bnlp\b|natural language|"
                    r"reinforcement learning|\brl\b|research (engineer|scientist)|applied scientist|"
                    r"\bai (engineer|researcher|scientist)|interpretab|alignment|pre-?training|post-?training|"
                    r"inference|robotic|perception|founding engineer|data scientist", re.I)

IRRELEVANT = re.compile(r"recruit\w*|talent|\bsales\b|account (executive|manager)|marketing|\blegal\b|counsel|"
                        r"attorney|finance|accountant|accounting|payroll|benefits|people (partner|systems|ops|operations)|"
                        r"\bhr\b|human resources|real estate|facilities|video editor|designer|copywriter|writer|"
                        r"\bcontent\b|compliance|\bgrc\b|risk analyst|enforcement analyst|economist|\bpolicy\b|"
                        r"product manag\w*|product management|program manager|project manager|"
                        r"operations (specialist|engineer, partnerships)|deployment specialist|strategist|partnerships|"
                        r"business systems|salesforce|\bit (support|operations)|support engineer|customer|"
                        r"solutions (engineer|consultant)|sales engineer|capacity planner|demand planning|"
                        r"procurement|manufacturing|quality engineer|hardware|silicon|data center|"
                        r"executive assistant|\boffice\b|research operations|product research specialist", re.I)

RELEVANT = re.compile(r"software (engineer|developer)|\bswe\b|backend|back-end|full[- ]?stack|"
                      r"platform engineer|infrastructure engineer|performance engineer|data engineer|"
                      r"ml ?ops|engineering intern|research intern|\bai\b|quant(itative)? (researcher|developer)", re.I)

BORDERLINE = re.compile(r"architect|analyst|security engineer|devops|\bsre\b|site reliability|cloud operations|"
                        r"systems engineer|product engineer|engineer\b", re.I)


# The job FUNCTION beats the topic: "Research Operations, Reinforcement Learning" is an ops job.
HARD_IRRELEVANT = re.compile(r"recruit\w*|research operations|\boperations (specialist|manager)|program manager|"
                             r"product manag\w*|product management|\bpolicy\b|economist|compliance|\blegal\b|"
                             r"\bsales\b|marketing|enforcement analyst|deployment specialist|strategist", re.I)
# Off-centre technical roles, checked before the generic "AI"/"software" match
# ("Applied AI Architect" is pre-sales architecture, not ML engineering).
BORDERLINE_SPECIFIC = re.compile(r"architect|analyst|security engineer|devops|\bsre\b|site reliability|"
                                 r"cloud operations|systems engineer|product engineer", re.I)


def role_relevance(title: str) -> str:
    if HARD_IRRELEVANT.search(title):
        return "irrelevant"
    if STRONG.search(title):
        return "relevant"
    if IRRELEVANT.search(title):
        return "irrelevant"
    if BORDERLINE_SPECIFIC.search(title):
        return "borderline"
    if RELEVANT.search(title):
        return "relevant"
    if BORDERLINE.search(title):
        return "borderline"
    return "irrelevant"
