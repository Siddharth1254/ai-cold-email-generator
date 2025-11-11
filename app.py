import os
from typing import Tuple

import requests
import streamlit as st
from dotenv import load_dotenv

from generate_email import generate_cold_email
from email_utils import send_email, validate_email_address


def _send_email_ui(receiver: str, subject: str, body: str) -> None:
	"""Handle the email sending UI and logic."""
	email_address = os.getenv("EMAIL_ADDRESS", "")
	email_password = os.getenv("EMAIL_PASSWORD", "")
	
	if not email_address:
		st.error("❌ EMAIL_ADDRESS not found in .env file. Please add it.")
		return
	
	if not email_password:
		st.error("❌ EMAIL_PASSWORD not found in .env file. Please add your Gmail app password.")
		return
	
	with st.spinner("Sending email..."):
		try:
			send_email(
				sender=email_address,
				receiver=receiver,
				subject=subject,
				body=body,
				password=email_password,
			)
			st.success(f"✅ Email sent successfully to {receiver}!")
		except ValueError as e:
			st.error(f"❌ Validation error: {e}")
		except RuntimeError as e:
			st.error(f"❌ {e}")
		except Exception as e:
			st.error(f"❌ Failed to send email: {e}")


def main() -> None:
	load_dotenv()
	st.set_page_config(page_title="AI Cold Email Generator", page_icon="📧", layout="centered")
	st.title("AI Cold Email Generator")
	st.caption("Powered by Mistral API")

	with st.form("cold_email_form"):
		col1, col2 = st.columns(2)
		with col1:
			prospect_name: str = st.text_input("Prospect name", placeholder="Jane Doe")
			company_name: str = st.text_input("Company", placeholder="Acme Inc.")
			prospect_role: str = st.text_input("Prospect role", placeholder="Head of Marketing")
		with col2:
			prospect_email: str = st.text_input("Prospect email (optional)", placeholder="jane@acme.com")
			tone: str = st.selectbox("Tone", ["Concise", "Friendly", "Professional", "Curious"], index=0)
			call_to_action: str = st.selectbox("Call to action", ["15-min intro call", "Reply to this email", "Try a demo", "Forward to the right person"], index=0)

		product_description: str = st.text_area(
			"Your product/service (what it does, key outcomes)",
			placeholder="AI tool that personalizes cold emails to increase reply rates by 2x",
			height=100,
		)
		pain_points: str = st.text_area(
			"Prospect pains / context (optional)",
			placeholder="Spending time on manual outreach, low reply rates, limited personalization",
			height=100,
		)

		submit: bool = st.form_submit_button("Generate email")

	if submit:
		if prospect_email and not validate_email_address(prospect_email):
			st.error("Please enter a valid email address or leave it empty.")
			st.stop()

		with st.spinner("Generating with Mistral..."):
			try:
				subject, body = generate_cold_email(
					company_name=company_name.strip(),
					prospect_name=prospect_name.strip(),
					prospect_role=prospect_role.strip(),
					product_description=product_description.strip(),
					pain_points=pain_points.strip(),
					tone=tone,
					call_to_action=call_to_action,
				)
			except requests.exceptions.HTTPError as e:
				error_msg = str(e).lower()
				if "429" in error_msg or "rate limit" in error_msg:
					st.error("🚦 Mistral API is temporarily overloaded. Please try again in a few minutes.")
				else:
					st.error(f"Failed to generate email: {e}")
				st.stop()
			except RuntimeError as e:
				error_msg = str(e).lower()
				if "429" in error_msg or "rate limit" in error_msg:
					st.error("🚦 Mistral API is temporarily overloaded. Please try again in a few minutes.")
				else:
					st.error(f"Failed to generate email: {e}")
				st.stop()
			except Exception as exc:  # noqa: BLE001
				st.error(f"Failed to generate email: {exc}")
				st.stop()

		# Store in session state for sending later
		st.session_state["subject"] = subject
		st.session_state["email_body"] = body
		st.session_state["receiver"] = prospect_email if prospect_email else ""

	# Display generated email if it exists in session state
	if st.session_state.get("subject") and st.session_state.get("email_body"):
		st.divider()
		st.subheader("Generated Email")
		
		subject = st.session_state["subject"]
		body = st.session_state["email_body"]
		receiver = st.session_state.get("receiver", "")
		
		st.subheader("Subject")
		st.code(subject or "", language=None)

		st.subheader("Email Body")
		st.text_area("", body or "", height=300, key="email_body_display", disabled=True)

		col1, col2 = st.columns(2)
		with col1:
			st.download_button(
				label="📥 Download as .txt",
				data=f"Subject: {subject}\n\n{body}",
				file_name="cold_email.txt",
				mime="text/plain",
			)
		with col2:
			if receiver and validate_email_address(receiver):
				if st.button("📧 Send Email", type="primary", key="send_email_btn"):
					_send_email_ui(receiver, subject, body)
			else:
				st.info("💡 Enter a valid recipient email above to enable sending.")


if __name__ == "__main__":
	main()


