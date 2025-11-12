import os
import time
from typing import Tuple

import requests
from dotenv import load_dotenv

from email_utils import parse_subject_and_body


load_dotenv()

MISTRAL_API_KEY: str | None = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_CHAT_URL: str = os.getenv("MISTRAL_CHAT_URL", "https://api.mistral.ai/v1/chat/completions")
MAX_RETRIES: int = 3
RETRY_DELAY: int = 5  # seconds


def _make_api_request(headers: dict, payload: dict) -> requests.Response:
    """Make API request with retry mechanism for rate limiting (429 errors)."""
    for attempt in range(MAX_RETRIES):
        response = requests.post(MISTRAL_CHAT_URL, headers=headers, json=payload, timeout=30)

        if response.status_code == 429:
            if attempt < MAX_RETRIES - 1:
                print(f"Rate limit hit. Waiting {RETRY_DELAY} seconds before retry...")
                time.sleep(RETRY_DELAY)
                continue
            msg = f"Mistral API rate limit exceeded after {MAX_RETRIES} attempts: {response.text}"
            raise RuntimeError(msg)

        if response.status_code >= 400:
            raise RuntimeError(f"Mistral API error {response.status_code}: {response.text}")

        return response

    raise RuntimeError(f"Failed to get successful response after {MAX_RETRIES} attempts")


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

    response = _make_api_request(headers, payload)
    data = response.json()
    try:
        content: str = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unexpected Mistral response format: {data}") from exc

    return parse_subject_and_body(content)


def generate_email(company: str, role: str, sender: str, receiver: str, position: str) -> dict[str, str]:
    """Generate a professional job/internship cold email using Mistral API.

    Returns a dict with keys: "subject" and "body".
    """
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
                "You write concise, polite job/internship outreach emails that are professional, "
                "personalized, and specific. Keep body under 140 words, avoid buzzwords, "
                "and propose a simple next step (e.g., brief call or sharing a portfolio). "
                "Do not use brackets, placeholders, or template markers. "
                "Return output strictly as:\n"
                "Subject: <one-line subject>\n\n<body paragraphs>"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a short, polite cold email from {sender} to {receiver} at {company} about the {role} position. "
                "Avoid any brackets, placeholder phrases, or template markers. "
                f"{sender} is pursuing the {position} opportunity at {company}, and wants to express genuine interest, "
                "highlight a relevant strength, and ask for a simple next step such as a quick call. "
                "Make sure the email feels tailored to this scenario."
            ),
        },
    ]

    payload = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 500,
    }

    response = _make_api_request(headers, payload)
    data = response.json()
    try:
        content: str = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unexpected Mistral response format: {data}") from exc

    subject, body = parse_subject_and_body(content)
    return {"subject": subject, "body": body}

