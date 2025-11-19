import os
import time
from collections import deque
from typing import Tuple

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


def _ensure_circuit_allows_call() -> None:
    now = time.time()
    if now < _circuit_open_until:
        wait_seconds = int(_circuit_open_until - now)
        logger.warning("Circuit breaker active; skipping LLM call for %s more seconds.", wait_seconds)
        raise RuntimeError("LLM temporarily unavailable due to repeated failures. Please try again later.")


def _record_failure() -> None:
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
    if _failure_timestamps:
        _failure_timestamps.clear()


def _invoke_with_fallback(headers: dict, payload: dict) -> requests.Response:
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


def _sanitize_optional_field(value: str | None) -> str | None:
    if not value:
        return None
    sanitized = value.strip()[:200]
    return sanitized or None


def _build_user_prompt(
    company_name: str,
    prospect_name: str,
    prospect_role: str,
    product_description: str,
    pain_points: str,
    tone: str,
    call_to_action: str,
) -> str:
    sections: list[str] = [
        f"Company: {company_name}",
        f"Prospect: {prospect_name} ({prospect_role})",
        f"Product: {product_description}",
        f"Tone: {tone}",
        f"CTA: {call_to_action}",
    ]
    if pain_points:
        sections.append(f"Prospect pains: {pain_points}")
    return "\n".join(sections)


def generate_cold_email(
    company_name: str,
    prospect_name: str,
    prospect_role: str,
    product_description: str,
    pain_points: str,
    tone: str,
    call_to_action: str,
) -> Tuple[str, str]:
    """Generate a subject and body for a cold email using Mistral Chat API."""
    logger.info(
        "generate_cold_email request: company=%s prospect=%s role=%s",
        company_name,
        prospect_name,
        prospect_role,
    )
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not set. Add it to your .env file.")

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert SDR helping craft short, high-conversion cold emails. "
                "Return output in this exact format:\n"
                "Subject: <one-line subject>\n\n<body paragraphs>"
            ),
        },
        {
            "role": "user",
            "content": (
                "Write a first-touch cold email based on the following context. "
                "Keep it under 120 words, personalize naturally, avoid fluff, and end with the CTA.\n\n"
                + _build_user_prompt(
                    company_name=company_name,
                    prospect_name=prospect_name,
                    prospect_role=prospect_role,
                    product_description=product_description,
                    pain_points=pain_points,
                    tone=tone,
                    call_to_action=call_to_action,
                )
            ),
        },
    ]

    payload = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 600,
    }

    response = _invoke_with_fallback(headers, payload)
    data = response.json()
    try:
        content: str = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected response format from Mistral during cold email generation.")
        raise RuntimeError(f"Unexpected Mistral response format: {data}") from exc

    return parse_subject_and_body(content)


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
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }

    position_text = f"the {position} opportunity" if position else "an opportunity"
    details_parts: list[str] = []
    if company_note:
        note = company_note.strip()[:200]
        if note:
            details_parts.append(f"Include this company insight: {note}. ")
    if one_liner:
        strength = one_liner.strip()[:200]
        if strength:
            details_parts.append(f"Highlight this strength: {strength}. ")
    if how_found:
        found = how_found.strip()[:200]
        if found:
            details_parts.append(f"Mention how the sender found the opportunity: {found}. ")
    details_string = "".join(details_parts)
    signature_instruction = (
        f"End the email with the exact signature: 'Best, {sender_name}' — "
        "do NOT output placeholders or brackets. Use the exact sender_name value provided. "
        "Never use '[Your Name]', '[Name]', or any placeholder text for the signature."
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You write concise, polite job/internship outreach emails that are professional, "
                "personalized, and specific. Keep body under 140 words, avoid buzzwords, "
                "and propose a simple next step (e.g., brief call or sharing a portfolio). "
                "Do not use brackets, placeholders, or template markers. "
                f"{signature_instruction} "
                "Return output strictly as:\n"
                "Subject: <one-line subject>\n\n<body paragraphs>"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a short, polite cold email from {sender_name} ({sender_email}) to {receiver_email} at {company} about the {role} position. "
                "Avoid any brackets, placeholder phrases, or template markers. "
                f"{sender_name} is pursuing {position_text} at {company}, and wants to express genuine interest, "
                "highlight a relevant strength, and ask for a simple next step such as a quick call. "
                f"{details_string}"
                "Make sure the email feels tailored to this scenario. "
                f"{signature_instruction}"
            ),
        },
    ]

    payload = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 500,
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

