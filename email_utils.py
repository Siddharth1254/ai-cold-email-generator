import os
import re
import smtplib
from typing import BinaryIO, Optional, Tuple

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


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


def send_email(
	sender: str,
	receiver: str,
	subject: str,
	body: str,
	password: str,
	file: Optional[BinaryIO] = None,
) -> None:
	"""Send an email via Gmail SMTP with optional attachment.
	
	Args:
		sender: Sender email address
		receiver: Receiver email address
		subject: Email subject
		body: Email body text
		password: Gmail app password
		file: Optional file attachment (BinaryIO)
	
	Raises:
		smtplib.SMTPException: If email sending fails
		ValueError: If email addresses are invalid
	"""
	if not validate_email_address(sender):
		raise ValueError(f"Invalid sender email address: {sender}")
	if not validate_email_address(receiver):
		raise ValueError(f"Invalid receiver email address: {receiver}")
	
	if not subject or not body:
		raise ValueError("Subject and body cannot be empty")
	
	if not password:
		raise ValueError("Password is required")
	
	msg = MIMEMultipart()
	msg["From"] = sender
	msg["To"] = receiver
	msg["Subject"] = subject
	
	msg.attach(MIMEText(body, "plain"))
	
	if file:
		try:
			file_data = file.read()
			part = MIMEApplication(file_data, Name=os.path.basename(file.name))
			part["Content-Disposition"] = f'attachment; filename="{os.path.basename(file.name)}"'
			msg.attach(part)
		except Exception as e:
			raise RuntimeError(f"Failed to attach file: {e}") from e
	
	try:
		with smtplib.SMTP("smtp.gmail.com", 587) as server:
			server.starttls()
			server.login(sender, password)
			server.send_message(msg)
	except smtplib.SMTPAuthenticationError as e:
		raise RuntimeError(
			"Authentication failed. Please check your email and app password."
		) from e
	except smtplib.SMTPRecipientsRefused as e:
		raise RuntimeError(f"Invalid recipient email address: {receiver}") from e
	except smtplib.SMTPServerDisconnected as e:
		raise RuntimeError("Connection to email server lost. Please try again.") from e
	except smtplib.SMTPException as e:
		raise RuntimeError(f"Failed to send email: {e}") from e
	except Exception as e:
		raise RuntimeError(f"Unexpected error while sending email: {e}") from e

