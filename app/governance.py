import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GovernanceDecision:
    allowed: bool
    policy_action: str
    severity: str
    risk_score: float
    categories: list[str] = field(default_factory=list)
    findings: list[dict[str, str]] = field(default_factory=list)
    sanitized_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "policy_action": self.policy_action,
            "severity": self.severity,
            "risk_score": self.risk_score,
            "categories": self.categories,
            "findings": self.findings,
            "sanitized_message": self.sanitized_message,
        }


class GovernanceGateway:
    def __init__(self) -> None:
        self.prompt_injection_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b",
                r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+instructions\b",
                r"\breveal\s+(the\s+)?(system|developer)\s+(prompt|message|instructions)\b",
                r"\bshow\s+(me\s+)?(the\s+)?(system|developer)\s+(prompt|message)\b",
                r"\bjailbreak\b",
                r"\bbypass\s+(the\s+)?(policy|guardrail|safety)\b",
                r"\bdo\s+anything\s+now\b",
                r"\bact\s+as\s+(dan|an\s+unrestricted|a\s+malicious)\b",
            ]
        ]
        self.secret_patterns = [
            ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
            ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
            (
                "private_key",
                re.compile(r"-----BEGIN\s+(RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
            ),
            (
                "credential_phrase",
                re.compile(r"\b(secret|access[_ -]?token|api[_ -]?key|password)\s*[:=]\s*\S+", re.IGNORECASE),
            ),
        ]
        self.pii_patterns = [
            ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
            ("phone", re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")),
            ("long_number", re.compile(r"(?<!\d)\d{13,19}(?!\d)")),
        ]
        self.destructive_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"\bdelete\s+all\b",
                r"\bdrop\s+database\b",
                r"\bexfiltrate\b",
                r"\bsteal\b",
                r"\bdisable\s+(the\s+)?(guardrail|security|logging|audit)\b",
                r"\bturn\s+off\s+(cloudtrail|logging|guardduty|security\s+hub)\b",
            ]
        ]

    def evaluate(self, message: str) -> GovernanceDecision:
        categories: list[str] = []
        findings: list[dict[str, str]] = []
        risk_score = 0.0

        injection_matches = self._matched_patterns(message, self.prompt_injection_patterns)
        if injection_matches:
            categories.append("prompt_injection")
            risk_score += 0.45
            findings.append(
                {
                    "category": "prompt_injection",
                    "severity": "high",
                    "signal": "Instruction override or prompt disclosure attempt detected.",
                }
            )

        secret_matches = self._matched_named_patterns(message, self.secret_patterns)
        if secret_matches:
            categories.append("secret")
            risk_score += 0.5
            findings.append(
                {
                    "category": "secret",
                    "severity": "critical",
                    "signal": f"Potential credential material detected: {', '.join(secret_matches)}.",
                }
            )

        pii_matches = self._matched_named_patterns(message, self.pii_patterns)
        if pii_matches:
            categories.append("pii")
            risk_score += 0.25
            findings.append(
                {
                    "category": "pii",
                    "severity": "medium",
                    "signal": f"Potential sensitive personal data detected: {', '.join(pii_matches)}.",
                }
            )

        destructive_matches = self._matched_patterns(message, self.destructive_patterns)
        if destructive_matches:
            categories.append("destructive_intent")
            risk_score += 0.55
            findings.append(
                {
                    "category": "destructive_intent",
                    "severity": "high",
                    "signal": "Destructive or unauthorized operational intent detected.",
                }
            )

        risk_score = round(min(1.0, risk_score), 2)
        policy_action = self._policy_action(categories, risk_score)
        severity = self._severity(risk_score, policy_action)
        return GovernanceDecision(
            allowed=policy_action != "block",
            policy_action=policy_action,
            severity=severity,
            risk_score=risk_score,
            categories=categories,
            findings=findings,
            sanitized_message=self._sanitize(message),
        )

    def _policy_action(self, categories: list[str], risk_score: float) -> str:
        if "secret" in categories:
            return "block"
        if "prompt_injection" in categories:
            return "block"
        if "destructive_intent" in categories and "prompt_injection" in categories:
            return "block"
        if risk_score >= 0.75:
            return "block"
        if risk_score >= 0.4:
            return "review"
        return "allow"

    def _severity(self, risk_score: float, policy_action: str) -> str:
        if policy_action == "block":
            return "critical"
        if risk_score >= 0.4:
            return "high"
        if risk_score > 0:
            return "medium"
        return "low"

    def _sanitize(self, message: str) -> str:
        sanitized = message
        replacements = [
            (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
            (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"), "[REDACTED_GITHUB_TOKEN]"),
            (
                re.compile(r"-----BEGIN\s+(RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
                "[REDACTED_PRIVATE_KEY]",
            ),
            (
                re.compile(r"\b(secret|access[_ -]?token|api[_ -]?key|password)\s*[:=]\s*\S+", re.IGNORECASE),
                "[REDACTED_SECRET]",
            ),
            (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
            (re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)"), "[REDACTED_PHONE_OR_NUMBER]"),
            (re.compile(r"(?<!\d)\d{13,19}(?!\d)"), "[REDACTED_NUMBER]"),
        ]
        for pattern, replacement in replacements:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    def _matched_patterns(self, message: str, patterns: list[re.Pattern[str]]) -> list[str]:
        return [pattern.pattern for pattern in patterns if pattern.search(message)]

    def _matched_named_patterns(self, message: str, patterns: list[tuple[str, re.Pattern[str]]]) -> list[str]:
        return [name for name, pattern in patterns if pattern.search(message)]
