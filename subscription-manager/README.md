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

1. User enters email
2. Email is validated (@inspection.gc.ca)
3. Email is added/removed from local state
4. GitHub secrets are updated automatically

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
python app.py
```

## Configuration (.env)

```env
# GitHub (required)
GITHUB_TOKEN=your-token-with-repo-and-workflow-permissions
GITHUB_REPO=ai-cfia/insect-project

# Initial email list (JSON array)
INITIAL_EMAILS_LIST=["email1@inspection.gc.ca","email2@inspection.gc.ca"]
```

## Usage

- **Web interface**: `http://localhost:5000`
- **API**: `GET /api/subscribers/count` for subscriber count

## Testing

Run the complete test suite:

```bash
# Install test dependencies
pip install pytest

# Run all tests (uses .env.example for safe test configuration)
pytest test_app.py -v
```

Tests use `.env.example` for configuration (no real credentials needed).

**Test coverage:**

- ✅ Email validation (@inspection.gc.ca only)
- ✅ Subscribe/unsubscribe workflow
- ✅ Token generation and validation
- ✅ GitHub API integration (mocked)
- ✅ File operations (init/state files)
- ✅ Web interface endpoints
- ✅ Edge cases and error handling

- Required email validation
- GitHub secrets encryption
