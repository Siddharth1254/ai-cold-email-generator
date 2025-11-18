import os

import requests
import streamlit as st
from dotenv import load_dotenv

from generate_email import generate_email
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
	st.set_page_config(page_title="AI Cold Email Generator", page_icon="📧", layout="wide")
	st.title("AI Cold Email Generator")
	st.caption("Powered by Mistral API")

	# Lightweight UI styling
	st.markdown(
		"""
		<style>
		.block-container {
			padding-top: 2rem;
			padding-bottom: 2rem;
		}
		.stTextInput>div>div>input,
		.stTextArea>div>div>textarea {
			border-radius: 6px;
			border: 1px solid #d0d4dc;
			padding: 0.35rem 0.6rem;
		}
		</style>
		""",
		unsafe_allow_html=True,
	)

	# Initialize sender_name from EMAIL_ADDRESS if not in session state
	if "sender_name" not in st.session_state:
		email_address = os.getenv("EMAIL_ADDRESS", "")
		if email_address:
			local_part = email_address.split("@")[0]
			sender_name_default = local_part.replace(".", " ").replace("_", " ").title()
			st.session_state["sender_name"] = sender_name_default
		else:
			st.session_state["sender_name"] = ""

	# Initialize sender_email and generated email session state
	if "sender_email" not in st.session_state:
		st.session_state["sender_email"] = os.getenv("EMAIL_ADDRESS", "")
	if "receiver_email" not in st.session_state:
		st.session_state["receiver_email"] = ""
	if "generated_subject" not in st.session_state:
		st.session_state["generated_subject"] = ""
	if "generated_body" not in st.session_state:
		st.session_state["generated_body"] = ""

	left_col, right_col = st.columns(2)

	# Left column: inputs and generate button
	with left_col:
		st.subheader("Email Details")
		with st.form("email_form"):
			sender_email = st.text_input(
				"Your email",
				value=st.session_state.get("sender_email", ""),
				key="sender_email_input",
			)
			sender_name = st.text_input(
				"Your full name",
				value=st.session_state.get("sender_name", ""),
				key="sender_name_input",
			)
			receiver_email = st.text_input(
				"Recipient email",
				value=st.session_state.get("receiver_email", ""),
				key="receiver_email_input",
			)
			company_name: str = st.text_input("Company", placeholder="Acme Inc.")
			prospect_role: str = st.text_input("Role / Team", placeholder="Head of Marketing")
			position: str = st.text_input("Position (optional)", placeholder="Summer 2026 Marketing Intern")

			attachment = st.file_uploader("Attachment (optional)", key="attachment")

			generate_clicked: bool = st.form_submit_button("Generate Email", type="primary")

		# Persist basic fields in session state
		st.session_state["sender_email"] = sender_email
		st.session_state["sender_name"] = sender_name
		st.session_state["receiver_email"] = receiver_email

		if generate_clicked:
			if not sender_email or not validate_email_address(sender_email):
				st.error("Please enter a valid sender email address.")
				st.stop()

			if not receiver_email or not validate_email_address(receiver_email):
				st.error("Please enter a valid recipient email address.")
				st.stop()

			if not sender_name:
				st.error("Please enter your full name.")
				st.stop()

			if not company_name:
				st.error("Please enter a company.")
				st.stop()

			if not prospect_role:
				st.error("Please enter a role or team.")
				st.stop()

			with st.spinner("Generating with Mistral..."):
				try:
					result = generate_email(
						company=company_name.strip(),
						role=prospect_role.strip(),
						sender_email=sender_email.strip(),
						receiver_email=receiver_email.strip(),
						position=position.strip() if position else None,
						sender_name=sender_name.strip(),
					)
					st.session_state["generated_subject"] = result.get("subject", "").strip()
					st.session_state["generated_body"] = result.get("body", "").strip()
					st.success("Generated — edit below if needed")
				except requests.exceptions.HTTPError as e:
					error_msg = str(e).lower()
					if "429" in error_msg or "rate limit" in error_msg:
						st.error("🚦 Mistral API is temporarily overloaded. Please try again in a few minutes.")
					else:
						st.error(f"Failed to generate email: {e}")
				except RuntimeError as e:
					error_msg = str(e).lower()
					if "429" in error_msg or "rate limit" in error_msg:
						st.error("🚦 Mistral API is temporarily overloaded. Please try again in a few minutes.")
					else:
						st.error(f"Failed to generate email: {e}")
				except Exception as exc:  # noqa: BLE001
					st.error(f"Failed to generate email: {exc}")

	# Right column: editable subject/body and send button
	with right_col:
		st.subheader("Preview & Send")

		subject_value = st.text_input("Subject", key="generated_subject")
		body_value = st.text_area("Email body", key="generated_body", height=300)

		receiver_email = st.session_state.get("receiver_email", "")

		if st.button("📧 Send Email", type="primary", key="send_email_btn"):
			if not receiver_email or not validate_email_address(receiver_email):
				st.error("Please enter a valid recipient email address on the left first.")
			elif not subject_value or not body_value:
				st.error("Subject and body cannot be empty.")
			else:
				_send_email_ui(receiver_email, subject_value, body_value)


if __name__ == "__main__":
	main()


