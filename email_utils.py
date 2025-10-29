import re
from typing import Tuple


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def validate_email_address(email: str) -> bool:
	if not email:
		return False
	return bool(_EMAIL_RE.match(email.strip()))


def parse_subject_and_body(model_output: str) -> Tuple[str, str]:
	"""Parse LLM output into (subject, body).

	Accepts outputs like:
	Subject: Something

	body text here
	"""
	text = model_output.strip()
	if not text:
		return "", ""

	lines = [ln.rstrip() for ln in text.splitlines()]

	subject = ""
	body_lines: list[str] = []
	if lines and lines[0].lower().startswith("subject:"):
		subject = lines[0].split(":", 1)[1].strip()
		body_lines = lines[1:]
	else:
		# Fallback: use first non-empty line as subject, rest as body
		for idx, ln in enumerate(lines):
			if ln.strip():
				subject = ln.strip()
				body_lines = lines[idx + 1 :]
				break

	body = "\n".join(body_lines).lstrip("\n")
	return subject, body


