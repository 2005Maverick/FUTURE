"""Shared prompt-injection guards for every agent that reads fetched text (E-11).

Fetched postings and messages are data, never instructions. The model is the first
line of defence; these deterministic checks are the second, so a fooled output still
cannot steer a decision or carry injected text into the digest.
"""
from __future__ import annotations

import re

# Phrases addressed to an AI reader rather than to a human applicant. Kept narrow on
# purpose: ordinary postings never say these, so a hit is a strong signal.
INJECTION = re.compile(r"""
      \bignore\s+(?:all\s+|any\s+|your\s+|the\s+)?(?:previous\s+|prior\s+|above\s+|earlier\s+|extraction\s+|screening\s+|system\s+)?(?:instructions|rules|prompts?)
    | \bdisregard\s+(?:all\s+|any\s+|your\s+|the\s+)?(?:previous|prior|above|earlier)
    | \b(?:admin|administrator|system|developer)\s+(?:override|mode|instruction|message)
    | \bnew\s+instructions?\s+from
    | \bnote\s+to\s+(?:the\s+)?(?:reviewer|screener|screening|recruiting|hiring)?\s*(?:ai|bot|model|llm|assistant)\b
    | \b(?:ai|llm|language\s+model)\s+(?:assistants?|screeners?|reviewers?|agents?)\s+(?:reading|processing|screening|reviewing|parsing)
    | \b(?:bots|ai\s+assistants?|llms?)\s+(?:and|or)\s+(?:ai\s+assistants?|bots|llms?)\b
    | \byou\s+are\s+now\s+(?:a\s+|an\s+|the\s+)?\w*(?:bot|gpt|ai|assistant|agent)\b
    | \b(?:candidate|applicant)\s+(?:has\s+)?already\s+(?:been\s+)?approved
    | (?:^|[\n.!?>:-]\s*)(?:system|assistant|extractor|evaluator)\s*:
    | \brate\s+(?:this\s+|the\s+)?(?:fit|candidate|posting|application)\s+(?:as\s+)?\d
""", re.IGNORECASE | re.VERBOSE)

URL_OR_EMAIL = re.compile(r"(?:https?://|www\.)\S+|\b[\w.+-]+@[\w-]+\.[\w.-]+\b|\b[\w-]+\.(?:example|com|io|ai|in|co|org|net)/\S*",
                          re.IGNORECASE)
INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")
SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")


def has_injection(text: str | None) -> bool:
    return bool(INJECTION.search(INVISIBLE.sub("", text or "")))


def fence(text: str) -> str:
    """Neutralise the data-block delimiters so untrusted text cannot close the block
    early and continue as if it were outside it."""
    return re.sub(r">{3,}", "›››", re.sub(r"<{3,}", "‹‹‹", text))


def scrub(text: str) -> str:
    """Remove links, email addresses and any sentence that addresses an AI reader."""
    kept = [s for s in SENTENCE.findall(INVISIBLE.sub("", text or "")) if not INJECTION.search(s)]
    return re.sub(r"\s{2,}", " ", URL_OR_EMAIL.sub("", "".join(kept))).strip()
