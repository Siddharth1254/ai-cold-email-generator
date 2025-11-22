import os
import time
from collections import deque

import requests
from dotenv import load_dotenv

from email_utils import parse_subject_and_body
from logger import logger


load_dotenv()

MISTRAL_API_KEY: str | None = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_CHAT_URL: str = os.getenv("MISTRAL_CHAT_URL", "https://api.mistral.ai/v1/chat/completions")
FALLBACK_MODEL: str = os.getenv("MISTRAL_FALLBACK_MODEL", "mistral-tiny-latest")
MAX_RETRIES: int = 3
RETRY_DELAY: int = 5  # seconds
FAILURE_THRESHOLD: int = 3
FAILURE_WINDOW_SECONDS: int = 60
CIRCUIT_BREAKER_COOLDOWN: int = 300

_failure_timestamps: deque[float] = deque()
_circuit_open_until: float = 0.0

# API request template
HEADERS_TEMPLATE = {
    "Content-Type": "application/json",
}


# Circuit breaker helpers
def _ensure_circuit_allows_call() -> None:
    """Check if circuit breaker allows API call, raise if circuit is open."""
    now = time.time()
    if now < _circuit_open_until:
        wait_seconds = int(_circuit_open_until - now)
        logger.warning("Circuit breaker active; skipping LLM call for %s more seconds.", wait_seconds)
        raise RuntimeError("LLM temporarily unavailable due to repeated failures. Please try again later.")


def _record_failure() -> None:
    """Record a failure and open circuit breaker if threshold is reached."""
    global _circuit_open_until
    now = time.time()
    _failure_timestamps.append(now)
    while _failure_timestamps and now - _failure_timestamps[0] > FAILURE_WINDOW_SECONDS:
        _failure_timestamps.popleft()
    if len(_failure_timestamps) >= FAILURE_THRESHOLD:
        _circuit_open_until = now + CIRCUIT_BREAKER_COOLDOWN
        _failure_timestamps.clear()
        logger.warning(
            "Opened LLM circuit breaker for %s seconds after %s failures within %s seconds.",
            CIRCUIT_BREAKER_COOLDOWN,
            FAILURE_THRESHOLD,
            FAILURE_WINDOW_SECONDS,
        )


def _record_success() -> None:
    """Clear failure timestamps on successful API call."""
    if _failure_timestamps:
        _failure_timestamps.clear()


# API request helpers
def _make_api_request(headers: dict, payload: dict) -> requests.Response:
    """Make API request with retry mechanism for rate limiting (429 errors)."""
    for attempt in range(MAX_RETRIES):
        response = requests.post(MISTRAL_CHAT_URL, headers=headers, json=payload, timeout=30)

        if response.status_code == 429:
            logger.warning(
                "Mistral rate limit hit (attempt %s/%s). Retrying in %s seconds.",
                attempt + 1,
                MAX_RETRIES,
                RETRY_DELAY,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            msg = f"Mistral API rate limit exceeded after {MAX_RETRIES} attempts: {response.text}"
            logger.error(msg)
            raise RuntimeError(msg)

        if response.status_code >= 400:
            logger.error("Mistral API error %s: %s", response.status_code, response.text)
            raise RuntimeError(f"Mistral API error {response.status_code}: {response.text}")

        return response

    logger.error("Failed to get successful response after %s attempts", MAX_RETRIES)
    raise RuntimeError(f"Failed to get successful response after {MAX_RETRIES} attempts")


def _invoke_with_fallback(headers: dict, payload: dict) -> requests.Response:
    """Invoke API with fallback model on failure."""
    _ensure_circuit_allows_call()
    try:
        response = _make_api_request(headers, payload)
        _record_success()
        return response
    except Exception:
        logger.exception("Primary model %s failed.", payload.get("model"))
        _record_failure()
        if payload.get("model") != FALLBACK_MODEL:
            fallback_payload = dict(payload)
            fallback_payload["model"] = FALLBACK_MODEL
            logger.warning("Trying fallback model %s", FALLBACK_MODEL)
            _ensure_circuit_allows_call()
            try:
                response = _make_api_request(headers, fallback_payload)
                _record_success()
                return response
            except Exception:
                logger.exception("Fallback model %s also failed.", FALLBACK_MODEL)
                _record_failure()
                raise
        raise


# Prompt helper functions
def _system_prompt(sender_name: str) -> str:
    """Return clean system instructions controlling tone, structure, constraints."""
    return f"""You write concise, polite job/internship outreach emails that are professional, personalized, and specific.

Requirements:
• Keep body under 140 words
• Emails must sound confident, concise, and mature
• Avoid "soft" language like "just reaching out", "hope you're doing well", or anything apologetic
• No generic compliments such as "your company is amazing"
• Prioritize clarity over friendliness; polite but not chummy
• Use short sentences. Avoid long intros. No fluff
• Propose a simple next step (e.g., brief call or sharing a portfolio)
• Maximum 2 short paragraphs
• Do not use brackets, placeholders, or template markers
• End the email with the exact signature: 'Best, {sender_name}' — do NOT output placeholders or brackets. Use the exact sender_name value provided. Never use '[Your Name]', '[Name]', or any placeholder text for the signature.

Guardrails:
• Do not invent roles, skills, or achievements that were not provided
• Do not fabricate details
• If information is missing, omit it without guessing
• Never output placeholders like [Name], [Company], or template markers
• If sender skills/achievements are not provided, do not describe them
• If company details are not provided, do not invent them
• If role responsibilities are unknown, do not state them

Ban these generic phrases:
• "I hope you are doing well"
• "I am writing to express"
• "I would love the opportunity"
• "Passionate"
• "Dynamic"
• "Innovative company"
• Any filler corporate jargon

Replace generic statements with specific, factual lines.

Subject line rules:
Subject lines must follow ONE of these patterns:
• "Quick question about <ROLE>"
• "<COMPANY>: regarding <ROLE>"
• "<ROLE> — brief note"
• "Intro from <SENDER_NAME>"

Constraints:
• 3 to 7 words
• No emojis
• No placeholders
• No hype words like "Exciting opportunity"

CTA rules:
CTA must be one of these:
• Ask for a 10-minute call
• Offer to share portfolio/github
• Ask who the correct contact is

CTA must be in the final paragraph only.
CTA must be a single sentence.

Output format:
Subject: <one-line subject>

<body paragraphs>"""


def _user_prompt(
    sender_name: str,
    sender_email: str,
    receiver_email: str,
    company: str,
    role: str,
    position: str | None,
    how_found: str | None,
    one_liner: str | None,
    company_note: str | None,
) -> str:
    """Return user-specific structured email context with optional fields included only when present."""
    lines = [
        "Write a short, polite cold email with the following details:",
        "",
        "Sender name:",
        sender_name,
        "",
        "Sender email:",
        sender_email,
        "",
        "Recipient email:",
        receiver_email,
        "",
        "Company:",
        company,
        "",
        "Role:",
        role,
    ]
    
    if position:
        lines.extend([
            "",
            "Position:",
            position,
        ])
    
    optional_details = _format_optional_details(how_found, one_liner, company_note)
    if optional_details:
        lines.extend([
            "",
            optional_details,
        ])
    
    lines.extend([
        "",
        "Email structure:",
        "1. One-sentence opening with purpose",
        "2. One short paragraph with personalization",
        "3. One short paragraph with the sender's relevant strength",
        "4. One-sentence CTA",
        "5. Signature",
        "",
        "Each section must be separated by a blank line.",
        "",
        "Personalization rules:",
        "• Only include optional fields if they fit naturally",
        "• Do not force details into the first sentence",
        "• Company insight should be 1 sentence max",
        "• One-liner (strength) must be integrated into the body, not the subject line",
        "• \"How found\" must appear late in the email, never in the opening line",
        "",
        "Make sure the email feels tailored to this scenario and expresses genuine interest.",
    ])
    
    return "\n".join(lines)


def _sanitize_optional_field(value: str | None) -> str | None:
    """Sanitize optional field: strip and limit to 200 characters."""
    if not value:
        return None
    sanitized = value.strip()[:200]
    return sanitized or None


def _format_optional_details(
    how_found: str | None,
    one_liner: str | None,
    company_note: str | None,
) -> str:
    """Format optional details into a structured block.
    
    Returns a formatted string with bullet points for existing fields,
    or empty string if no fields are provided.
    """
    details = []
    if company_note:
        details.append(f"- Company insight: {company_note}")
    if one_liner:
        details.append(f"- Highlight: {one_liner}")
    if how_found:
        details.append(f"- How found: {how_found}")
    
    if not details:
        return ""
    
    return "Extra details:\n" + "\n".join(details)


# Main generation function
def generate_email(
    company: str,
    role: str,
    sender_email: str,
    receiver_email: str,
    position: str | None = None,
    sender_name: str | None = None,
    how_found: str | None = None,
    one_liner: str | None = None,
    company_note: str | None = None,
) -> dict[str, str]:
    """Generate a professional job/internship cold email using Mistral API.

    Returns a dict with keys: "subject" and "body".
    """
    logger.info(
        "generate_email request: company=%s role=%s sender=%s receiver=%s",
        company,
        role,
        sender_email,
        receiver_email,
    )
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not set. Add it to your .env file.")

    if not sender_name:
        raise ValueError("sender_name is required and cannot be None or empty")
    position = _sanitize_optional_field(position)
    how_found = _sanitize_optional_field(how_found)
    one_liner = _sanitize_optional_field(one_liner)
    company_note = _sanitize_optional_field(company_note)

    headers = {
        **HEADERS_TEMPLATE,
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
    }

    messages = [
        {"role": "system", "content": _system_prompt(sender_name)},
        {
            "role": "user",
            "content": _user_prompt(
                sender_name=sender_name,
                sender_email=sender_email,
                receiver_email=receiver_email,
                company=company,
                role=role,
                position=position,
                how_found=how_found,
                one_liner=one_liner,
                company_note=company_note,
            ),
        },
    ]

    payload = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 450,
    }

    response = _invoke_with_fallback(headers, payload)
    data = response.json()
    try:
        content: str = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected response format from Mistral during job email generation.")
        raise RuntimeError(f"Unexpected Mistral response format: {data}") from exc

    subject, body = parse_subject_and_body(content)
    return {"subject": subject, "body": body}

