"""Location parsing for job postings: which countries, and is it remote (and
remote *where*)? Deterministic keyword rules; ambiguous cases stay ambiguous
rather than being guessed."""
from __future__ import annotations

import re
from dataclasses import dataclass

INDIA = re.compile(r"\b(india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|new delhi|gurgaon|gurugram|noida|"
                   r"chennai|kolkata|ahmedabad|kochi|jaipur|indore|chandigarh|dehradun)\b", re.I)
COUNTRY_PATTERNS = {
    "IN": INDIA,
    "US": re.compile(r"\b(united states|usa|u\.s\.|us-|us only|\bus\b|new york|nyc|san francisco|seattle|austin|"
                     r"boston|chicago|denver|los angeles|atlanta|washington|bay area|"
                     r",\s?(ca|ny|wa|tx|ma|il|co|ga|or|nc|va|nj|pa|fl|ut|az|mn|mi|dc))\b", re.I),
    "GB": re.compile(r"\b(united kingdom|\buk\b|london|manchester|edinburgh|england)\b", re.I),
    "CA": re.compile(r"\b(canada|toronto|vancouver|ontario|montreal|waterloo|\bcan\b)\b", re.I),
    "IE": re.compile(r"\b(ireland|dublin)\b", re.I),
    "DE": re.compile(r"\b(germany|berlin|munich)\b", re.I),
    "FR": re.compile(r"\b(france|paris)\b", re.I),
    "NL": re.compile(r"\b(netherlands|amsterdam)\b", re.I),
    "SG": re.compile(r"\b(singapore)\b", re.I),
    "JP": re.compile(r"\b(japan|tokyo)\b", re.I),
    "AU": re.compile(r"\b(australia|sydney|melbourne)\b", re.I),
    "BR": re.compile(r"\b(brazil|são paulo|sao paulo)\b", re.I),
    "MX": re.compile(r"\b(mexico)\b", re.I),
    "ES": re.compile(r"\b(spain|madrid|barcelona)\b", re.I),
    "PL": re.compile(r"\b(poland|warsaw)\b", re.I),
    "AE": re.compile(r"\b(uae|dubai|abu dhabi)\b", re.I),
    "CH": re.compile(r"\b(switzerland|z(u|ü|�)rich|zurich|geneva|lausanne|\bch\b)", re.I),
    "SE": re.compile(r"\b(sweden|stockholm)\b", re.I),
    "KR": re.compile(r"\b(south korea|korea|seoul)\b", re.I),
    "IL": re.compile(r"\b(israel|tel aviv)\b", re.I),
    "HK": re.compile(r"\b(hong kong)\b", re.I),
    "QA": re.compile(r"\b(qatar|doha)\b", re.I),
}
REGION = re.compile(r"\b(emea|apac|asia|europe|latam|americas|anywhere|worldwide|global)\b", re.I)
REMOTE = re.compile(r"\bremote|work from home|wfh|distributed\b", re.I)
REGIONS_INCLUDING_INDIA = {"apac", "asia", "anywhere", "worldwide", "global"}


@dataclass(frozen=True)
class ParsedLocation:
    raw: str
    countries: frozenset[str]
    remote: bool
    regions: frozenset[str]

    @property
    def in_india(self) -> bool:
        return "IN" in self.countries

    @property
    def remote_scope(self) -> str:
        """'india_ok' | 'restricted' | 'unspecified' | 'none'."""
        if not self.remote:
            return "none"
        if self.in_india or self.regions & REGIONS_INCLUDING_INDIA:
            return "india_ok"
        if self.countries or self.regions:
            return "restricted"
        return "unspecified"


def parse_location(*parts: str) -> ParsedLocation:
    raw = " | ".join(p for p in parts if p)
    countries = frozenset(code for code, pat in COUNTRY_PATTERNS.items() if pat.search(raw))
    regions = frozenset(m.lower() for m in REGION.findall(raw))
    return ParsedLocation(raw=raw, countries=countries, remote=bool(REMOTE.search(raw)), regions=regions)
