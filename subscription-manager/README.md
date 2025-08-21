# Email Subscription Manager

Web application for managing subscriptions to automated Insect Project reports.

## Features

- **Subscribe/Unsubscribe** with email validation
- **Domain restriction**: Only `@inspection.gc.ca` emails
- **Secure tokens** with 24h expiration
- **Automatic GitHub synchronization**

## How it works

### Initialization (first startup)

1. If `emails_state.json` doesn't exist:
   - App reads `INITIAL_EMAILS_LIST` from `.env`
   - Filters to keep only `@inspection.gc.ca` emails
   - Creates `init_emails.json` then `emails_state.json`

### Normal operation

1. App uses `emails_state.json` as local source of truth
2. On each modification (subscribe/unsubscribe):
   - Updates `emails_state.json`
   - Updates GitHub secrets `COMMENTS_EMAIL_RECIPIENTS` and `OBSERVATIONS_EMAIL_RECIPIENTS`
3. GitHub workflows use the updated secrets

### Subscribe/unsubscribe flow

1. User enters email → Token generated and stored in Redis
2. Confirmation email sent
3. User clicks link → Email added/removed + GitHub secrets updated

## Quick installation

### With Docker

```bash
cp .env.example .env
# Edit .env (see Configuration section)
docker-compose up --build
```

### Local

```bash
pip install -r requirements.txt
redis-server
python app.py
```

## Configuration (.env)

```env
# GitHub (required)
GITHUB_TOKEN=your-token-with-repo-and-workflow-permissions
GITHUB_REPO=ai-cfia/insect-project

# Initial email list (JSON array)
INITIAL_EMAILS_LIST=["email1@inspection.gc.ca","email2@inspection.gc.ca"]

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# SMTP (for confirmation emails)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com  
SMTP_PASSWORD=your-app-password
```

## Usage

- **Web interface**: `http://localhost:5000`
- **API**: `GET /api/subscribers/count` for subscriber count

## Security

- Required email validation
- Temporary tokens (24h)
- GitHub secrets encryption
