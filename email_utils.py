import os
import re
import smtplib
from typing import BinaryIO, Optional, Tuple

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from email_validator import EmailNotValidError, validate_email

from logger import logger


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def is_valid_email(email: str) -> Tuple[bool, Optional[str]]:
	if not email or not email.strip():
		return False, "Email address is required."
	try:
		validate_email(email, check_deliverability=False)
		return True, None
	except EmailNotValidError as exc:
		return False, str(exc)


def validate_email_address(email: str) -> bool:
	valid, _ = is_valid_email(email)
	return valid


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
) -> Tuple[bool, str]:
	"""Send an email via Gmail SMTP with optional attachment.
	
	Args:
		sender: Sender email address
		receiver: Receiver email address
		subject: Email subject
		body: Email body text
		password: Gmail app password
		file: Optional file attachment (BinaryIO)
	
	Returns:
		Tuple[bool, str]: True and success message, otherwise raises error.

	Raises:
		smtplib.SMTPException: If email sending fails
		ValueError: If email addresses are invalid
	"""
	valid_sender, sender_error = is_valid_email(sender)
	if not valid_sender:
		raise ValueError(f"Invalid sender email address: {sender_error}")
	valid_receiver, receiver_error = is_valid_email(receiver)
	if not valid_receiver:
		raise ValueError(f"Invalid receiver email address: {receiver_error}")
	
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
			file.seek(0)
			file_data = file.read()
			filename = os.path.basename(getattr(file, "name", "attachment"))
			part = MIMEApplication(file_data, Name=filename)
			part["Content-Disposition"] = f'attachment; filename="{filename}"'
			msg.attach(part)
			logger.info("Attached file '%s' to outgoing email.", filename)
		except Exception as e:
			logger.exception("Failed to attach file to email.")
			raise RuntimeError(f"Failed to attach file: {e}") from e
	
	logger.info("Sending email from %s to %s", sender, receiver)
	try:
		with smtplib.SMTP("smtp.gmail.com", 587) as server:
			server.starttls()
			server.login(sender, password)
			server.send_message(msg)
		return True, f"✅ Email sent successfully to {receiver}!"
	except smtplib.SMTPAuthenticationError as e:
		logger.exception("SMTP authentication failed for sender %s", sender)
		raise RuntimeError(
			"Authentication failed. Please check your email and app password."
		) from e
	except smtplib.SMTPRecipientsRefused as e:
		logger.exception("SMTP recipient refused: %s", receiver)
		raise RuntimeError(f"Invalid recipient email address: {receiver}") from e
	except smtplib.SMTPServerDisconnected as e:
		logger.exception("SMTP server disconnected unexpectedly.")
		raise RuntimeError("Connection to email server lost. Please try again.") from e
	except smtplib.SMTPException as e:
		logger.exception("SMTP exception occurred while sending email.")
		raise RuntimeError(f"Failed to send email: {e}") from e
	except Exception as e:
		logger.exception("Unexpected exception occurred while sending email.")
		raise RuntimeError(f"Unexpected error while sending email: {e}") from e

