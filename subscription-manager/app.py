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
# import redis  # No longer needed without email confirmation

load_dotenv()

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'ai-cfia/insect-project')
GITHUB_SECRETS = ['COMMENTS_EMAIL_RECIPIENTS', 'OBSERVATIONS_EMAIL_RECIPIENTS']

SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@inspection.gc.ca')

# TOKEN_EXPIRY_HOURS = 24  # No longer needed

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))


# Redis client removed - no longer needed without email confirmation

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
    
    # Update both environment secrets
    environment_name = "dev"  # Change this if using different environment
    for secret_name in GITHUB_SECRETS:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/environments/{environment_name}/secrets/{secret_name}"
        response = requests.put(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"✓ Updated {secret_name} in environment {environment_name}")
    
    # Update local state file
    os.makedirs('data', exist_ok=True)
    state_file = 'data/emails_state.json'
    with open(state_file, 'w') as f:
        json.dump({'emails': emails_list, 'updated_at': datetime.now().isoformat()}, f, indent=2)
    
    return True

# Token generation removed - no longer needed

# Email confirmation function removed - no longer needed

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
        
        # Direct subscription without email confirmation
        print(f"DEBUG: Adding email {email} to list")
        emails.append(email)
        try:
            print(f"DEBUG: Updating GitHub secrets with {len(emails)} emails")
            update_github_secrets(emails)
            print(f"DEBUG: Successfully updated GitHub secrets")
            flash('You have been successfully subscribed!', 'success')
        except Exception as e:
            flash('Error updating subscription. Please try again later.', 'error')
            print(f"ERROR updating GitHub secrets: {e}")
            import traceback
            traceback.print_exc()
        
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
        
        # Direct unsubscription without email confirmation
        print(f"DEBUG: Removing email {email} from list")
        emails.remove(email)
        try:
            print(f"DEBUG: Updating GitHub secrets with {len(emails)} emails")
            update_github_secrets(emails)
            print(f"DEBUG: Successfully updated GitHub secrets")
            flash('You have been successfully unsubscribed.', 'success')
        except Exception as e:
            flash('Error updating subscription. Please try again later.', 'error')
            print(f"ERROR updating GitHub secrets: {e}")
            import traceback
            traceback.print_exc()
        
        return redirect(url_for('index'))
    
    return render_template('unsubscribe.html')

# Removed confirm_subscribe route - no longer needed with direct subscription

# Removed confirm_unsubscribe route - no longer needed with direct unsubscription

@app.route('/api/subscribers/count')
def api_subscriber_count():
    emails = get_current_emails()
    return jsonify({'count': len(emails)})

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true')
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
