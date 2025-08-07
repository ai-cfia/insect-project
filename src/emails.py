import email.utils
import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from smtplib import SMTP

import pandas as pd
from jinja2 import Template
from pydantic import EmailStr, validate_call
from tqdm import tqdm

from src.custom_logging import log_call
from src.pydantic_models import EmailTable
from src.settings import Settings

log = logging.getLogger(__name__)


@validate_call
def sanitize_html_links(html: str):
    """Replace HTML link targets with simple URL text"""
    return re.sub('target="_blank".+?>', "> URL </a>", html)


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def render_email_body(template: Template, tables: list[EmailTable], empty_message: str):
    """Render HTML email body from template and tables"""
    html = template.render(tables=tables, empty_message=empty_message)
    html = sanitize_html_links(html)
    return html


@log_call
@validate_call
def send_smtp_emails(s: Settings, recipients: list[EmailStr], subject: str, body: str):
    """Send HTML emails via SMTP to multiple recipients"""
    with SMTP(s.smtp_host, s.smtp_port) as server:
        server.set_debuglevel(s.smtp_debug_level)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(s.smtp_username, s.smtp_password.get_secret_value())
        for recipient in tqdm(recipients, desc="Sending emails"):
            log.info(f"Sending email to {recipient}")
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = email.utils.formataddr((s.sender_name, s.sender_email))
            message["To"] = recipient
            message.attach(MIMEText(body, "html"))
            server.sendmail(s.sender_email, recipient, message.as_string())


if __name__ == "__main__":
    # run with "python -m src.emails"
    import argparse

    from dotenv import load_dotenv
    from jinja2 import Template

    load_dotenv()
    parser = argparse.ArgumentParser(description="Email testing and sending utility")
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send emails (default: just render and print)",
    )
    parser.add_argument(
        "--recipients", nargs="+", help="Email recipients (required if --send is used)"
    )
    parser.add_argument(
        "--subject", default="Test Email from Insect Project", help="Email subject line"
    )
    parser.add_argument(
        "--template",
        choices=["simple", "full"],
        default="simple",
        help="Template to use: 'simple' for basic HTML, 'full' for complete template",
    )
    args = parser.parse_args()
    if args.send and not args.recipients:
        parser.error("--recipients is required when --send is used")
    settings = Settings()
    data = {
        "upper taxa": ["Insecta", "Plantae", "Mollusca", "Other"],
        "name": ["Species A", "Species B", "Species C", "Species D"],
        "link": ["http://a.com", "http://b.com", "http://c.com", "http://d.com"],
    }
    df = pd.DataFrame(data)
    html = df.to_html(index=False, escape=False)
    tables = [EmailTable(title="Test Table", html=html)]
    if args.template == "full":
        try:
            template = settings.observations_email_body_template
        except Exception as e:
            log.warning(
                f"Could not load full template: {e}. Falling back to simple template."
            )
            template = Template(
                "{{ tables[0].title }}<br>{{ tables[0].html }}", autoescape=True
            )
    else:
        template = Template(
            "{{ tables[0].title }}<br>{{ tables[0].html }}", autoescape=True
        )
    body = render_email_body(template, tables, empty_message="No data.")
    print("Email Body:")
    print(body)
    if args.send:
        print(f"\nSending emails to: {', '.join(args.recipients)}")
        try:
            send_smtp_emails(settings, args.recipients, args.subject, body)
            print("✅ Emails sent successfully!")
        except Exception as e:
            print(f"❌ Failed to send emails: {e}")
            log.error(f"Email sending failed: {e}")
    else:
        print(
            "\n💡 To send real emails, use: python -m src.emails --send --recipients recipient@example.com"
        )
