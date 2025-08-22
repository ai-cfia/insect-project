import os
import json
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import requests
from nacl import encoding, public
from dotenv import load_dotenv
import redis

load_dotenv()

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'ai-cfia/insect-project')
GITHUB_SECRETS = ['COMMENTS_EMAIL_RECIPIENTS', 'OBSERVATIONS_EMAIL_RECIPIENTS']

SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@inspection.gc.ca')

TOKEN_EXPIRY_HOURS = 24

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))


redis_client = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    db=0,
    decode_responses=True
)

def encrypt_secret_for_repository(public_key: str, secret_value: str) -> str:
    """Encrypt a secret using a repository's public key."""
    public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return encoding.Base64Encoder().encode(encrypted).decode("utf-8")

def get_github_public_key():
    """Get the repository's public key for secrets encryption."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/secrets/public-key"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_current_emails():
    """Get current email list from local state file."""
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    state_file = 'data/emails_state.json'
    init_file = 'data/init_emails.json'
    
    # Check if state file exists, if not initialize
    if not os.path.exists(state_file):
        # Try to create init_emails.json from environment variable first
        if not os.path.exists(init_file):
            create_init_emails_from_env()
        
        try:
            # Initialize from init file
            with open(init_file, 'r') as f:
                init_data = json.load(f)
            
            # Convert emails to lowercase
            emails_lower = [email.lower() for email in init_data.get('emails', [])]
            init_data['emails'] = emails_lower
            
            # Create state file
            with open(state_file, 'w') as f:
                json.dump(init_data, f, indent=2)
            
            return emails_lower
        except FileNotFoundError:
            # No init file, start with empty list
            return []
    
    # Read from state file
    try:
        with open(state_file, 'r') as f:
            data = json.load(f)
            return data.get('emails', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def create_init_emails_from_env():
    """Create init_emails.json from INITIAL_EMAILS_LIST environment variable."""
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    init_file = 'data/init_emails.json'
    initial_emails_env = os.environ.get('INITIAL_EMAILS_LIST')
    
    if initial_emails_env:
        try:
            # Parse the environment variable as JSON
            initial_emails = json.loads(initial_emails_env)
            
            # Filter to only keep @inspection.gc.ca emails and convert to lowercase
            filtered_emails = [email.lower() for email in initial_emails if email.lower().endswith('@inspection.gc.ca')]
            
            init_data = {
                "emails": filtered_emails,
                "updated_at": datetime.now().isoformat()
            }
            
            # Create init_emails.json
            with open(init_file, 'w') as f:
                json.dump(init_data, f, indent=2)
            
            print(f"Created {init_file} with {len(filtered_emails)} emails from environment")
            
        except json.JSONDecodeError as e:
            print(f"Error parsing INITIAL_EMAILS_LIST: {e}")
        except Exception as e:
            print(f"Error creating {init_file}: {e}")
    else:
        # Create empty init file
        init_data = {
            "emails": [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(init_file, 'w') as f:
            json.dump(init_data, f, indent=2)
        
        print(f"Created empty {init_file} - no INITIAL_EMAILS_LIST provided")

def update_github_secrets(emails_list):
    """Update both GitHub secrets with new email list."""
    public_key_data = get_github_public_key()
    
    encrypted_value = encrypt_secret_for_repository(
        public_key_data['key'],
        json.dumps(emails_list)
    )
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "encrypted_value": encrypted_value,
        "key_id": public_key_data['key_id']
    }
    
    # Update both secrets
    for secret_name in GITHUB_SECRETS:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/secrets/{secret_name}"
        response = requests.put(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"✓ Updated {secret_name}")
    
    # Update local state file
    os.makedirs('data', exist_ok=True)
    state_file = 'data/emails_state.json'
    with open(state_file, 'w') as f:
        json.dump({'emails': emails_list, 'updated_at': datetime.now().isoformat()}, f, indent=2)
    
    return True

def generate_token():
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)

def send_confirmation_email(email, token, action='subscribe'):
    """Send confirmation email with token."""
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print(f"Email configuration missing, token for {email}: {token}")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = email
        msg['Subject'] = f"Confirm your {'subscription' if action == 'subscribe' else 'unsubscription'} - Insect Project Reports"
        
        if action == 'subscribe':
            link = f"{request.url_root}confirm_subscribe?token={token}&email={email}"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #2c3e50;">Confirm Your Subscription</h2>
                        <p>Hello,</p>
                        <p>You have requested to subscribe to the Insect Project automated reports from the Canadian Food Inspection Agency (CFIA).</p>
                        <p>To complete your subscription, please confirm by clicking the button below:</p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{link}" style="background-color: #4CAF50; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">Confirm Subscription</a>
                        </div>
                        <p style="color: #666; font-size: 14px;">If the button doesn't work, copy and paste this link into your browser:</p>
                        <p style="color: #666; font-size: 12px; word-break: break-all;">{link}</p>
                        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                        <p style="color: #999; font-size: 12px;">This confirmation link will expire in {TOKEN_EXPIRY_HOURS} hours.</p>
                        <p style="color: #999; font-size: 12px;">If you did not request this subscription, please ignore this email.</p>
                        <p style="color: #999; font-size: 12px;">Canadian Food Inspection Agency / Agence canadienne d'inspection des aliments</p>
                    </div>
                </body>
            </html>
            """
        else:
            link = f"{request.url_root}confirm_unsubscribe?token={token}&email={email}"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #2c3e50;">Confirm Your Unsubscription</h2>
                        <p>Hello,</p>
                        <p>You have requested to unsubscribe from the Insect Project automated reports.</p>
                        <p>To confirm your unsubscription, please click the button below:</p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{link}" style="background-color: #f44336; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">Confirm Unsubscription</a>
                        </div>
                        <p style="color: #666; font-size: 14px;">If the button doesn't work, copy and paste this link into your browser:</p>
                        <p style="color: #666; font-size: 12px; word-break: break-all;">{link}</p>
                        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                        <p style="color: #999; font-size: 12px;">This confirmation link will expire in {TOKEN_EXPIRY_HOURS} hours.</p>
                        <p style="color: #999; font-size: 12px;">If you did not request this unsubscription, please ignore this email.</p>
                        <p style="color: #999; font-size: 12px;">Canadian Food Inspection Agency / Agence canadienne d'inspection des aliments</p>
                    </div>
                </body>
            </html>
            """
        
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@app.route('/')
def index():
    emails = get_current_emails()
    return render_template('index.html', subscriber_count=len(emails))

@app.route('/subscribe', methods=['GET', 'POST'])
def subscribe():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('subscribe'))
        
        # Validate domain - must be @inspection.gc.ca
        if not email.endswith('@inspection.gc.ca'):
            flash('Email must be from @inspection.gc.ca domain.', 'error')
            return redirect(url_for('subscribe'))
        
        emails = get_current_emails()
        
        if email in emails:
            flash('This email is already subscribed.', 'info')
            return redirect(url_for('index'))
        
        token = generate_token()
        redis_client.setex(
            f"subscribe_token:{token}",
            timedelta(hours=TOKEN_EXPIRY_HOURS),
            email
        )
        
        if send_confirmation_email(email, token, 'subscribe'):
            flash('A confirmation email has been sent. Please check your inbox.', 'success')
        else:
            flash('Error sending confirmation email. Please try again later.', 'error')
        
        return redirect(url_for('index'))
    
    return render_template('subscribe.html')

@app.route('/unsubscribe', methods=['GET', 'POST'])
def unsubscribe():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('unsubscribe'))
        
        # Validate domain - must be @inspection.gc.ca
        if not email.endswith('@inspection.gc.ca'):
            flash('Email must be from @inspection.gc.ca domain.', 'error')
            return redirect(url_for('unsubscribe'))
        
        emails = get_current_emails()
        
        if email not in emails:
            flash('This email is not subscribed.', 'info')
            return redirect(url_for('index'))
        
        token = generate_token()
        redis_client.setex(
            f"unsubscribe_token:{token}",
            timedelta(hours=TOKEN_EXPIRY_HOURS),
            email
        )
        
        if send_confirmation_email(email, token, 'unsubscribe'):
            flash('A confirmation email has been sent. Please check your inbox.', 'success')
        else:
            flash('Error sending confirmation email. Please try again later.', 'error')
        
        return redirect(url_for('index'))
    
    return render_template('unsubscribe.html')

@app.route('/confirm_subscribe')
def confirm_subscribe():
    token = request.args.get('token')
    email = request.args.get('email', '').strip().lower()
    
    if not token or not email:
        flash('Invalid confirmation link.', 'error')
        return redirect(url_for('index'))
    
    stored_email = redis_client.get(f"subscribe_token:{token}")
    
    if not stored_email or stored_email != email:
        flash('Invalid or expired confirmation link.', 'error')
        return redirect(url_for('index'))
    
    emails = get_current_emails()
    
    if email not in emails:
        emails.append(email)
        try:
            update_github_secrets(emails)
            redis_client.delete(f"subscribe_token:{token}")
            flash('You have been successfully subscribed!', 'success')
        except Exception as e:
            flash('Error updating subscription. Please try again later.', 'error')
            print(f"Error updating GitHub secrets: {e}")
    else:
        flash('You are already subscribed.', 'info')
    
    return redirect(url_for('index'))

@app.route('/confirm_unsubscribe')
def confirm_unsubscribe():
    token = request.args.get('token')
    email = request.args.get('email', '').strip().lower()
    
    if not token or not email:
        flash('Invalid confirmation link.', 'error')
        return redirect(url_for('index'))
    
    stored_email = redis_client.get(f"unsubscribe_token:{token}")
    
    if not stored_email or stored_email != email:
        flash('Invalid or expired confirmation link.', 'error')
        return redirect(url_for('index'))
    
    emails = get_current_emails()
    
    if email in emails:
        emails.remove(email)
        try:
            update_github_secrets(emails)
            redis_client.delete(f"unsubscribe_token:{token}")
            flash('You have been successfully unsubscribed.', 'success')
        except Exception as e:
            flash('Error updating subscription. Please try again later.', 'error')
            print(f"Error updating GitHub secrets: {e}")
    else:
        flash('You are not currently subscribed.', 'info')
    
    return redirect(url_for('index'))

@app.route('/api/subscribers/count')
def api_subscriber_count():
    emails = get_current_emails()
    return jsonify({'count': len(emails)})

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true')
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
