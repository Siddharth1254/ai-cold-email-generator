import os
from typing import Tuple

import streamlit as st
from dotenv import load_dotenv

from generate_email import generate_cold_email
from email_utils import validate_email_address


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
			except Exception as exc:  # noqa: BLE001
				st.error(f"Failed to generate email: {exc}")
				st.stop()

		st.subheader("Subject")
		st.code(subject or "", language=None)

		st.subheader("Email Body")
		st.text_area("", body or "", height=300)

		st.download_button(
			label="Download as .txt",
			data=f"Subject: {subject}\n\n{body}",
			file_name="cold_email.txt",
			mime="text/plain",
		)


if __name__ == "__main__":
	main()


