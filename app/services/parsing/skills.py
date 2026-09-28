"""Canonical skill vocabulary.

Lexical matching fails on spelling long before it fails on meaning: a JD saying "PostgreSQL"
and a CV saying "Postgres" is the same skill, and a keyword filter that misses it is exactly
the blunt-instrument problem HireBridge exists to fix (docs/00-product-brief.md §2).

Every skill string — from a parsed CV, a parsed JD, or a user edit — passes through
`canonical()` before it is stored or compared.
"""

from __future__ import annotations

import re

# canonical -> aliases. Keep aliases lowercase; matching is case-insensitive.
SKILL_ALIASES: dict[str, set[str]] = {
    "python": {"python3", "py"},
    "javascript": {"js", "ecmascript", "es6", "es2015"},
    "typescript": {"ts"},
    "nextjs": {"next.js", "next js", "next"},
    "nodejs": {"node.js", "node", "node js"},
    "react": {"react.js", "reactjs"},
    "fastapi": {"fast api"},
    "django": {"django rest framework", "drf"},
    "flask": set(),
    "postgres": {"postgresql", "psql", "postgre sql", "postgres sql"},
    "mysql": {"my sql"},
    "mongodb": {"mongo", "mongo db"},
    "redis": set(),
    "elasticsearch": {"elastic search", "es"},
    "docker": {"dockerized", "containerization"},
    "kubernetes": {"k8s", "kube"},
    "aws": {"amazon web services"},
    "gcp": {"google cloud", "google cloud platform"},
    "azure": {"microsoft azure"},
    "terraform": set(),
    "ci_cd": {"ci/cd", "cicd", "continuous integration", "continuous delivery"},
    "rest_api": {"rest", "restful", "rest apis", "restful api", "restful apis"},
    "graphql": {"graph ql"},
    "grpc": {"g-rpc"},
    "websockets": {"websocket", "web sockets"},
    "rag": {"retrieval augmented generation", "retrieval-augmented generation"},
    "llm": {"llms", "large language model", "large language models"},
    "langchain": {"lang chain"},
    "vector_search": {"vector database", "vector db", "semantic search", "embeddings search"},
    "prompt_engineering": {"prompting", "prompt design"},
    "machine_learning": {"ml", "machine-learning"},
    "deep_learning": {"dl", "neural networks"},
    "nlp": {"natural language processing"},
    "pytorch": {"torch"},
    "tensorflow": {"tf"},
    "pandas": set(),
    "numpy": set(),
    "sql": set(),
    "git": {"version control"},
    "linux": {"unix"},
    "celery": set(),
    "rabbitmq": {"rabbit mq"},
    "kafka": {"apache kafka"},
    "n8n": {"n8n.io"},
    "tailwind": {"tailwindcss", "tailwind css"},
    "html": {"html5"},
    "css": {"css3"},
    "figma": set(),
}

_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in SKILL_ALIASES.items():
    _LOOKUP[_canonical] = _canonical
    _LOOKUP[_canonical.replace("_", " ")] = _canonical
    for _alias in _aliases:
        _LOOKUP[_alias] = _canonical

_PUNCT = re.compile(r"[^a-z0-9+#. ]+")
_SPACE = re.compile(r"\s+")


def normalize(raw: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace. No alias resolution."""
    text = _PUNCT.sub(" ", raw.strip().lower())
    return _SPACE.sub(" ", text).strip()


def canonical(raw: str) -> str:
    """Resolve a skill string to its canonical form.

    An unknown skill returns its normalized form with spaces underscored, so new skills
    still compare consistently between a CV and a JD.
    """
    normalized = normalize(raw)
    if not normalized:
        return ""
    if hit := _LOOKUP.get(normalized):
        return hit
    stripped = normalized.rstrip("s")
    if hit := _LOOKUP.get(stripped):
        return hit
    return normalized.replace(" ", "_")


def canonical_set(values: object) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {c for v in values if isinstance(v, str) and (c := canonical(v))}


def extract_known_skills(text: str) -> set[str]:
    """Canonical skills *named* in free text, by their own name or a known alias.

    Used to build the profile's skill corpus, so a tool named only inside a bullet still
    counts as evidence the candidate has it.
    """
    haystack = f" {normalize(text)} "
    return {canon for surface, canon in _LOOKUP.items() if f" {surface} " in haystack}


# Phrases that evidence a skill without naming it. "Built a retrieval chatbot" is evidence
# of RAG; the candidate simply did not use the acronym.
#
# This is what makes the tailoring agent's allowed behaviour possible — restating a fact in
# the job description's vocabulary — without letting the job description license a claim.
# A skill is supported by the *profile*, never by the JD asking for it.
SKILL_EVIDENCE: dict[str, set[str]] = {
    "rag": {
        "retrieval chatbot", "retrieval augmented", "retrieval system", "retrieval pipeline",
        "semantic retrieval", "document question answering", "document q a",
        "knowledge base chatbot", "context retrieval",
    },
    "vector_search": {"similarity search", "nearest neighbour", "nearest neighbor", "embedding search"},
    "llm": {"language model", "gpt", "claude", "chatbot powered by"},
    "rest_api": {"http endpoints", "api endpoints", "web api"},
    "ci_cd": {"build pipeline", "deployment pipeline", "automated deploys"},
    "docker": {"containerised", "containerized", "container image"},
    "machine_learning": {"trained a model", "model training", "predictive model"},
    "nlp": {"text classification", "named entity", "sentiment analysis"},
    "prompt_engineering": {"prompt template", "system prompt", "few shot"},
}


def extract_implied_skills(text: str) -> set[str]:
    """Canonical skills *evidenced but not named* in free text."""
    haystack = f" {normalize(text)} "
    return {
        canon
        for canon, phrases in SKILL_EVIDENCE.items()
        if any(f" {phrase} " in haystack for phrase in phrases)
    }
