import os
import re
from collections import Counter
from datetime import datetime, timedelta

import requests
import streamlit as st
from dotenv import load_dotenv

from generate_email import generate_email
from email_utils import is_valid_email, send_email
from logger import logger


def _parse_analytics_from_logs(log_file_path: str = "logs/app.log") -> dict:
	"""Parse log file and extract analytics metrics.
	
	Returns a dictionary with:
	- total_emails_generated: int
	- total_emails_sent: int
	- emails_sent_today: int
	- emails_sent_this_week: int
	- tone_usage: dict[str, int] (defaults to empty if not found in logs)
	- top_companies: list[tuple[str, int]] (company name, count)
	"""
	metrics = {
		"total_emails_generated": 0,
		"total_emails_sent": 0,
		"emails_sent_today": 0,
		"emails_sent_this_week": 0,
		"tone_usage": {"Formal": 0, "Friendly": 0, "Startup": 0},
		"top_companies": [],
	}
	
	if not os.path.exists(log_file_path):
		return metrics
	
	now = datetime.now()
	today = now.date()
	week_ago = now - timedelta(days=7)
	
	companies = []
	tone_counts = {"Formal": 0, "Friendly": 0, "Startup": 0}
	
	try:
		with open(log_file_path, "r", encoding="utf-8") as f:
			for line in f:
				# Parse date from log line (format: YYYY-MM-DD HH:MM:SS,mmm)
				date_match = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})", line)
				if date_match:
					date_str = date_match.group(1)
					time_str = date_match.group(2)
					try:
						log_date = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S").date()
						log_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
					except ValueError:
						continue
				else:
					continue
				
				# Count email generations
				if "Generating email for company=" in line:
					metrics["total_emails_generated"] += 1
					# Extract company name
					company_match = re.search(r"company=([^,]+)", line)
					if company_match:
						company = company_match.group(1).strip()
						companies.append(company)
				
				# Count email sends
				if "Email successfully sent to" in line or "Email sent |" in line:
					metrics["total_emails_sent"] += 1
					if log_date == today:
						metrics["emails_sent_today"] += 1
					if log_datetime >= week_ago:
						metrics["emails_sent_this_week"] += 1
				
				# Extract tone from log lines
				if "tone=" in line:
					tone_match = re.search(r"tone=([^|\s]+)", line)
					if tone_match:
						tone = tone_match.group(1).strip()
						# Initialize tone if not in dict, then increment
						if tone not in tone_counts:
							tone_counts[tone] = 0
						tone_counts[tone] += 1
		
		# Count top companies
		company_counts = Counter(companies)
		metrics["top_companies"] = company_counts.most_common(10)
		
		# Update tone_usage with parsed counts, ensuring all default tones are present
		for default_tone in metrics["tone_usage"]:
			metrics["tone_usage"][default_tone] = tone_counts.get(default_tone, 0)
		# Also include any additional tones found in logs
		for tone, count in tone_counts.items():
			if tone not in metrics["tone_usage"]:
				metrics["tone_usage"][tone] = count
		
	except Exception as e:
		logger.exception("Error parsing analytics from log file: %s", e)
	
	return metrics


def _send_email_ui(receiver: str, subject: str, body: str, file=None, tone: str = "Formal") -> None:
	"""Handle the email sending UI and logic."""
	email_address = os.getenv("EMAIL_ADDRESS", "")
	email_password = os.getenv("EMAIL_PASSWORD", "")
	
	if not email_address:
		logger.error("EMAIL_ADDRESS env var missing; cannot send email.")
		st.error("❌ EMAIL_ADDRESS not found in .env file. Please add it.")
		return
	
	if not email_password:
		logger.error("EMAIL_PASSWORD env var missing; cannot send email.")
		st.error("❌ EMAIL_PASSWORD not found in .env file. Please add your Gmail app password.")
		return
	
	logger.info("Attempting to send email to %s", receiver)
	with st.spinner("Sending email..."):
		try:
			ok, message = send_email(
				sender=email_address,
				receiver=receiver,
				subject=subject,
				body=body,
				password=email_password,
				file=file,
			)
			if ok:
				logger.info(f"Email sent | tone={tone} | recipient={receiver}")
				st.success(message or f"✅ Email sent successfully to {receiver}!")
		except ValueError as e:
			logger.exception("Validation error while sending email to %s", receiver)
			st.error(f"❌ Validation error: {e}")
		except RuntimeError as e:
			logger.exception("Runtime error while sending email to %s", receiver)
			st.error(f"❌ {e}")
		except Exception:
			logger.exception("Unexpected failure while sending email to %s", receiver)
			st.error("❌ Failed to send email due to an unexpected error.")


def _render_email_generator() -> None:
	"""Render the email generator UI page."""
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
	if "uploaded_file" not in st.session_state:
		st.session_state["uploaded_file"] = None
	if "how_found" not in st.session_state:
		st.session_state["how_found"] = ""
	if "one_liner" not in st.session_state:
		st.session_state["one_liner"] = ""
	if "company_note" not in st.session_state:
		st.session_state["company_note"] = ""
	if "tone" not in st.session_state:
		st.session_state["tone"] = "Formal"

	left_col, right_col = st.columns([4, 6], gap="large")

	# Left column: inputs and generate button
	with left_col:
		# Tone Selector
		st.markdown("### Tone:")
		
		current_tone = st.session_state.get("tone", "Formal")
		
		st.markdown(f"""
		<div class="tone-wrapper">
			<button class="tone-btn {'selected' if current_tone=='Formal' else ''}" onclick="sendTone('Formal')">Formal</button>
			<button class="tone-btn {'selected' if current_tone=='Friendly' else ''}" onclick="sendTone('Friendly')">Friendly</button>
			<button class="tone-btn {'selected' if current_tone=='Startup' else ''}" onclick="sendTone('Startup')">Startup</button>
		</div>
		
		<script>
		function sendTone(value) {{
			fetch("/?tone=" + value)
				.then(() => window.parent.location.reload());
		}}
		</script>
		""", unsafe_allow_html=True)
		
		# Capture tone from query params
		query_params = st.experimental_get_query_params()
		if "tone" in query_params:
			st.session_state["tone"] = query_params["tone"][0]
		
		with st.form("email_form"):
			# Sender Details
			with st.expander("👤 Sender Details", expanded=True):
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
			
			# Recipient Details
			with st.expander("📬 Recipient Details", expanded=True):
				receiver_email = st.text_input(
					"Recipient email",
					value=st.session_state.get("receiver_email", ""),
					key="receiver_email_input",
				)
				company_name: str = st.text_input("Company", placeholder="Acme Inc.")
				prospect_role: str = st.text_input("Role / Team", placeholder="Head of Marketing")
				position: str = st.text_input("Position (optional)", placeholder="Summer 2026 Marketing Intern")
			
			# Personalization
			with st.expander("✨ Personalization (optional)", expanded=False):
				how_found: str = st.text_input(
					"How you found the role",
					value=st.session_state.get("how_found", ""),
					placeholder="e.g., LinkedIn job posting",
				)
				one_liner: str = st.text_input(
					"Your strength",
					value=st.session_state.get("one_liner", ""),
					placeholder="e.g., Built ML models that improved conversion by 30%",
				)
				company_note: str = st.text_input(
					"Company insight",
					value=st.session_state.get("company_note", ""),
					placeholder="e.g., Noticed your recent expansion into AI",
				)
			
			# Attachment
			with st.expander("📎 Attachment (optional)", expanded=False):
				uploaded_file = st.file_uploader(
					"Attach file",
					type=["pdf", "docx", "png", "jpg"],
					key="attachment",
					label_visibility="collapsed",
				)
				if uploaded_file is not None:
					st.session_state["uploaded_file"] = uploaded_file
				else:
					st.session_state["uploaded_file"] = None
			
			# Generate button in styled container
			st.markdown('<div class="generate-button-container">', unsafe_allow_html=True)
			generate_clicked: bool = st.form_submit_button("🚀 Generate Email", type="primary", use_container_width=True)
			st.markdown('</div>', unsafe_allow_html=True)

		# Persist basic fields in session state
		# Form variables are accessible after form closes
		try:
			st.session_state["sender_email"] = sender_email.strip()
			st.session_state["sender_name"] = sender_name.strip()
			st.session_state["receiver_email"] = receiver_email.strip()
			st.session_state["how_found"] = how_found.strip()[:200] if how_found else ""
			st.session_state["one_liner"] = one_liner.strip()[:200] if one_liner else ""
			st.session_state["company_note"] = company_note.strip()[:200] if company_note else ""
		except NameError:
			# Variables not yet defined (first run), skip
			pass

		if generate_clicked:
			sender_valid, sender_error = is_valid_email(sender_email.strip())
			if not sender_valid:
				st.error(f"Sender email looks invalid: {sender_error}")
				st.stop()

			receiver_valid, receiver_error = is_valid_email(receiver_email.strip())
			if not receiver_valid:
				st.error(f"Recipient email looks invalid: {receiver_error}")
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
					logger.info(
						"Generating email for company=%s, role=%s, sender=%s, receiver=%s",
						company_name,
						prospect_role,
						sender_email,
						receiver_email,
					)
					result = generate_email(
						company=company_name.strip(),
						role=prospect_role.strip(),
						sender_email=sender_email.strip(),
						receiver_email=receiver_email.strip(),
						position=position.strip() if position else None,
						sender_name=sender_name.strip(),
						how_found=how_found.strip() if how_found else None,
						one_liner=one_liner.strip() if one_liner else None,
						company_note=company_note.strip() if company_note else None,
						tone=st.session_state.get("tone", "Formal"),
					)
					st.session_state["generated_subject"] = result.get("subject", "").strip()
					st.session_state["generated_body"] = result.get("body", "").strip()
					st.success("Generated — edit below if needed")
				except requests.exceptions.HTTPError as e:
					logger.exception("HTTP error while generating email.")
					error_msg = str(e).lower()
					if "429" in error_msg or "rate limit" in error_msg:
						st.error("🚦 Mistral API is temporarily overloaded. Please try again in a few minutes.")
					else:
						st.error(f"Failed to generate email: {e}")
				except RuntimeError as e:
					logger.exception("Runtime error while generating email.")
					error_msg = str(e).lower()
					if "429" in error_msg or "rate limit" in error_msg:
						st.error("🚦 Mistral API is temporarily overloaded. Please try again in a few minutes.")
					else:
						st.error(f"Failed to generate email: {e}")
				except Exception:
					logger.exception("Unexpected error while generating email.")
					st.error("Failed to generate email due to an unexpected error.")

	# Right column: editable subject/body and send button
	with right_col:
		st.subheader("📝 Preview & Send")
		
		receiver_email = st.session_state.get("receiver_email", "")
		
		# Show placeholder if no email generated
		# Check session state directly (already initialized at top of function)
		if not st.session_state.get("generated_subject") and not st.session_state.get("generated_body"):
			st.markdown(
				"""
				<div class="placeholder-container">
					<div class="placeholder-icon">✉️</div>
					<h3>No email generated yet</h3>
					<p>Fill in the details on the left and click "Generate Email" to create your cold email.</p>
				</div>
				""",
				unsafe_allow_html=True,
			)
		else:
			# Show editable fields after generation
			# Using key parameter automatically syncs with session state (no value= needed)
			subject_value = st.text_input("Subject", key="generated_subject")
			body_value = st.text_area("Email body", key="generated_body", height=300)
			
			# Send button - disabled if subject or body is empty
			# Read from session state to get current values after user edits
			current_subject = st.session_state.get("generated_subject", "").strip()
			current_body = st.session_state.get("generated_body", "").strip()
			can_send = bool(current_subject and current_body and receiver_email)
			
			if st.button(
				"📧 Send Email",
				type="primary",
				key="send_email_btn",
				use_container_width=True,
				disabled=not can_send,
			):
				receiver_valid, receiver_error = is_valid_email(receiver_email)
				if not receiver_valid:
					st.error(f"Please enter a valid recipient email address first: {receiver_error}")
				elif not current_subject or not current_body:
					st.error("Subject and body cannot be empty.")
				else:
					logger.info("User requested to send email to %s", receiver_email)
					file_to_send = st.session_state.get("uploaded_file")
					current_tone = st.session_state.get("tone", "Formal")
					_send_email_ui(receiver_email, current_subject, current_body, file_to_send, tone=current_tone)
			
			if not can_send:
				if not receiver_email:
					st.info("💡 Enter a recipient email address on the left to enable sending.")
				elif not current_subject or not current_body:
					st.info("💡 Subject and body must be filled to send the email.")


def _render_analytics_dashboard() -> None:
	"""Render the analytics dashboard page."""
	st.title("📊 Analytics Dashboard")
	
	# Try to read analytics.json first, then fall back to logs/app.log
	analytics_file = "analytics.json"
	log_file = "logs/app.log"
	
	metrics = None
	if os.path.exists(analytics_file):
		try:
			import json
			with open(analytics_file, "r", encoding="utf-8") as f:
				metrics = json.load(f)
		except Exception as e:
			logger.exception("Error reading analytics.json: %s", e)
	
	# If analytics.json doesn't exist or failed to read, parse from logs
	if metrics is None:
		metrics = _parse_analytics_from_logs(log_file)
	
	# Display key metrics
	st.subheader("📈 Key Metrics")
	col1, col2, col3, col4 = st.columns(4)
	
	with col1:
		st.metric("Total Emails Generated", metrics["total_emails_generated"])
	with col2:
		st.metric("Total Emails Sent", metrics["total_emails_sent"])
	with col3:
		st.metric("Emails Sent Today", metrics["emails_sent_today"])
	with col4:
		st.metric("Emails Sent This Week", metrics["emails_sent_this_week"])
	
	# Tone usage chart
	st.subheader("🎨 Tone Usage")
	tone_data = metrics.get("tone_usage", {})
	if tone_data and any(tone_data.values()):
		# Convert to dict format for bar chart (Streamlit accepts dict directly)
		st.bar_chart(tone_data)
	else:
		st.info("No tone usage data available yet.")
	
	# Top companies
	st.subheader("🏢 Top Companies Contacted")
	top_companies = metrics.get("top_companies", [])
	if top_companies:
		# Convert list of tuples to list of dicts for dataframe
		companies_data = [{"Company": company, "Count": count} for company, count in top_companies]
		st.dataframe(companies_data, use_container_width=True, hide_index=True)
	else:
		st.info("No company data available yet.")


def main() -> None:
	load_dotenv()
	st.set_page_config(page_title="AI Cold Email Generator", page_icon="📧", layout="wide")
	
	# Enhanced UI styling
	st.markdown(
		"""
		<style>
		.block-container {
			padding-top: 3rem;
			padding-bottom: 3rem;
		}
		.stTextInput>div>div>input,
		.stTextArea>div>div>textarea {
			border-radius: 8px;
			border: 1px solid #d0d4dc;
			padding: 0.5rem 0.75rem;
		}
		[data-testid="stExpander"] {
			border: 1px solid #e0e4e8;
			border-radius: 8px;
			padding: 0.5rem;
			margin-bottom: 1rem;
		}
		.main-header {
			display: flex;
			justify-content: space-between;
			align-items: center;
			padding: 1.5rem 0;
			border-bottom: 2px solid #e0e4e8;
			margin-bottom: 2rem;
		}
		.header-left h1 {
			margin: 0;
			font-size: 2rem;
		}
		.header-left p {
			margin: 0.25rem 0 0 0;
			color: #666;
		}
		.github-link {
			padding: 0.5rem 1rem;
			background-color: #f0f0f0;
			border-radius: 6px;
			text-decoration: none;
			color: #333;
			font-size: 0.9rem;
		}
		.github-link:hover {
			background-color: #e0e0e0;
		}
		.generate-button-container {
			margin-top: 2rem;
			padding: 1rem;
			background-color: #f8f9fa;
			border-radius: 8px;
			border: 1px solid #e0e4e8;
		}
		.placeholder-container {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			padding: 4rem 2rem;
			text-align: center;
			color: #888;
		}
		.placeholder-icon {
			font-size: 4rem;
			margin-bottom: 1rem;
		}
		/* Sidebar hamburger button styling */
		[data-testid="stSidebar"] [data-testid="stHeader"] button {
			padding: 0.5rem;
			width: 2rem;
			height: 2rem;
			border: none;
			background-color: transparent;
		}
		[data-testid="stSidebar"] [data-testid="stHeader"] button:hover {
			background-color: #f0f0f0;
			border-radius: 4px;
		}
		.tone-wrapper {
			display: flex;
			gap: 0.8rem;
			padding: 0.5rem 0;
		}
		.tone-btn {
			border-radius: 9999px;
			padding: 0.5rem 1.4rem;
			font-size: 0.95rem;
			border: 1px solid #ddd;
			background: #f5f5f5;
			cursor: pointer;
			transition: all 0.2s ease;
		}
		.tone-btn:hover {
			background: #e9e9e9;
			transform: translateY(-2px);
		}
		.tone-btn.selected {
			background: #4a90e2 !important;
			color: white !important;
			border-color: #357abd !important;
			transform: translateY(-2px);
			font-weight: 600;
			box-shadow: 0 3px 8px rgba(74,144,226,0.35);
		}
		</style>
		""",
		unsafe_allow_html=True,
	)
	
	# Sidebar navigation
	page = st.sidebar.radio(
		"Navigation",
		["Email Generator", "Analytics Dashboard"],
		label_visibility="collapsed",
	)
	
	# Route to appropriate page
	if page == "Email Generator":
		# Header bar
		st.markdown(
			"""
			<div class="main-header">
				<div class="header-left">
					<h1>📧 AI Cold Email Generator</h1>
					<p>Powered by Mistral API</p>
				</div>
				<a href="https://github.com" target="_blank" class="github-link">View on GitHub</a>
			</div>
			""",
			unsafe_allow_html=True,
		)
		_render_email_generator()
	elif page == "Analytics Dashboard":
		_render_analytics_dashboard()


if __name__ == "__main__":
	main()


