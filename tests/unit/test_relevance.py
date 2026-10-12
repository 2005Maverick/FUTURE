"""Role relevance, pinned to REAL titles from the 2026-10-12 live audit that the
first version wrongly passed (regression cases) plus the ones it must keep."""
import pytest

from future.pipeline.relevance import role_relevance

IRRELEVANT = [
    "Recruiter, Applied AI", "Benefits Analyst", "Video Editor Intern", "Real Estate Analyst",
    "Product Management, Research", "Salesforce Developer", "US Public Sector Compliance, Security GRC",
    "Safeguards Enforcement Analyst, Child Safety", "Research Economist, Economic Research",
    "AI Deployment Specialist, Beneficial Deployments", "Applied AI Strategist, EMEA",
    "Support Engineer", "IT Support Engineer", "Manufacturing Quality Engineer, Data Center Power & Cooling",
    "Hardware Systems Architect", "Silicon Engineer", "Infrastructure Capacity Planner, Demand Planning",
    "Research Operations, Reinforcement Learning", "Product Research Specialist (W from Groww)",
    "Business Systems Analyst, New Product Introduction", "Associate Solutions Engineer, Okta",
    "Account Executive, Enterprise",
]
RELEVANT = [
    "Research Engineer, Chip Design RL (Reinforcement Learning)", "Machine Learning Infrastructure Engineer, Safeguards Research",
    "Research Scientist, Interpretability", "Software Engineer, Intern", "Software Engineer, AI Agents",
    "Data Engineer, Product", "Full-Stack Software Engineer, Reinforcement Learning", "Performance Engineer, GPU",
    "Pre-training Data Infrastructure Engineer", "Intermediate Backend Engineer, India", "Applied Scientist",
    "AI Research Intern", "LLM Engineer", "Data Scientist",
]
BORDERLINE = ["Applied AI Architect, Public Sector", "Site Reliability Engineer", "Security Engineer, Corporate Security",
              "Systems Engineer (Data Intelligence & Analytics Team)", "Cloud Operations Engineer"]


@pytest.mark.parametrize("title", IRRELEVANT)
def test_irrelevant(title):
    assert role_relevance(title) == "irrelevant"


@pytest.mark.parametrize("title", RELEVANT)
def test_relevant(title):
    assert role_relevance(title) == "relevant"


@pytest.mark.parametrize("title", BORDERLINE)
def test_borderline(title):
    assert role_relevance(title) == "borderline"
