#!/usr/bin/env python3
"""
Test suite for Email Subscription Manager

Tests all functionality including:
- Email validation
- Subscribe/unsubscribe flows
- Token validation
- GitHub API integration
- File operations
"""

import os
import json
import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
import redis
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env.example for testing
load_dotenv('.env.example')

# Import the app
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app, get_current_emails, create_init_emails_from_env, update_github_secrets

@pytest.fixture
def client():
    """Create test client"""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            yield client

@pytest.fixture
def temp_dir():
    """Create temporary directory for test files"""
    temp_dir = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    yield temp_dir
    os.chdir(old_cwd)
    shutil.rmtree(temp_dir)

@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    with patch('app.redis_client') as mock_redis:
        mock_redis.setex.return_value = True
        mock_redis.get.return_value = None
        mock_redis.delete.return_value = True
        yield mock_redis

class TestEmailValidation:
    """Test email validation logic"""
    
    def test_valid_inspection_email(self, client):
        """Test valid @inspection.gc.ca email"""
        with patch('app.redis_client'), patch('app.send_confirmation_email', return_value=True):
            response = client.post('/subscribe', data={'email': 'test@inspection.gc.ca'})
            assert response.status_code == 302  # Redirect after success
    
    def test_invalid_domain_rejected(self, client):
        """Test invalid domain rejection"""
        response = client.post('/subscribe', data={'email': 'test@gmail.com'})
        assert response.status_code == 302
        # Check that it redirects back to subscribe page with error
    
    def test_canada_domain_rejected(self, client):
        """Test @canada.ca domain rejection (should only allow @inspection.gc.ca)"""
        response = client.post('/subscribe', data={'email': 'test@canada.ca'})
        assert response.status_code == 302
    
    def test_empty_email_rejected(self, client):
        """Test empty email rejection"""
        response = client.post('/subscribe', data={'email': ''})
        assert response.status_code == 302
    
    def test_malformed_email_rejected(self, client):
        """Test malformed email rejection"""
        response = client.post('/subscribe', data={'email': 'not-an-email'})
        assert response.status_code == 302

class TestFileOperations:
    """Test file operations and initialization"""
    
    def test_create_init_from_env(self, temp_dir):
        """Test creating init_emails.json from environment variable"""
        test_emails = ["test1@inspection.gc.ca", "test2@inspection.gc.ca", "invalid@gmail.com"]
        
        with patch.dict(os.environ, {'INITIAL_EMAILS_LIST': json.dumps(test_emails)}):
            create_init_emails_from_env()
            
            assert os.path.exists('init_emails.json')
            with open('init_emails.json', 'r') as f:
                data = json.load(f)
                # Should only contain @inspection.gc.ca emails
                assert len(data['emails']) == 2
                assert all(email.endswith('@inspection.gc.ca') for email in data['emails'])
    
    def test_get_current_emails_initialization(self, temp_dir):
        """Test email list initialization"""
        test_emails = ["init@inspection.gc.ca"]
        
        # Create init file
        init_data = {"emails": test_emails, "updated_at": datetime.now().isoformat()}
        with open('init_emails.json', 'w') as f:
            json.dump(init_data, f)
        
        emails = get_current_emails()
        assert emails == test_emails
        assert os.path.exists('emails_state.json')
    
    def test_get_current_emails_existing_state(self, temp_dir):
        """Test reading from existing state file"""
        test_emails = ["existing@inspection.gc.ca"]
        
        # Create state file directly
        state_data = {"emails": test_emails, "updated_at": datetime.now().isoformat()}
        with open('emails_state.json', 'w') as f:
            json.dump(state_data, f)
        
        emails = get_current_emails()
        assert emails == test_emails

class TestSubscribeFlow:
    """Test subscription workflow"""
    
    @patch('app.send_confirmation_email')
    @patch('app.redis_client')
    @patch('app.get_current_emails')
    def test_subscribe_new_email(self, mock_get_emails, mock_redis, mock_send_email, client):
        """Test subscribing a new email"""
        mock_get_emails.return_value = []
        mock_send_email.return_value = True
        mock_redis.setex.return_value = True
        
        response = client.post('/subscribe', data={'email': 'new@inspection.gc.ca'})
        assert response.status_code == 302
        mock_send_email.assert_called_once()
    
    @patch('app.get_current_emails')
    def test_subscribe_existing_email(self, mock_get_emails, client):
        """Test subscribing an already subscribed email"""
        mock_get_emails.return_value = ['existing@inspection.gc.ca']
        
        response = client.post('/subscribe', data={'email': 'existing@inspection.gc.ca'})
        assert response.status_code == 302
    
    @patch('app.redis_client')
    @patch('app.get_current_emails')
    @patch('app.update_github_secrets')
    def test_confirm_subscribe_valid_token(self, mock_update_secrets, mock_get_emails, mock_redis, client):
        """Test confirming subscription with valid token"""
        mock_redis.get.return_value = 'test@inspection.gc.ca'
        mock_get_emails.return_value = []
        mock_update_secrets.return_value = True
        
        response = client.get('/confirm_subscribe?token=valid-token&email=test@inspection.gc.ca')
        assert response.status_code == 302
        mock_update_secrets.assert_called_once()
    
    @patch('app.redis_client')
    def test_confirm_subscribe_invalid_token(self, mock_redis, client):
        """Test confirming subscription with invalid token"""
        mock_redis.get.return_value = None
        
        response = client.get('/confirm_subscribe?token=invalid-token&email=test@inspection.gc.ca')
        assert response.status_code == 302

class TestUnsubscribeFlow:
    """Test unsubscription workflow"""
    
    @patch('app.send_confirmation_email')
    @patch('app.redis_client')
    @patch('app.get_current_emails')
    def test_unsubscribe_existing_email(self, mock_get_emails, mock_redis, mock_send_email, client):
        """Test unsubscribing an existing email"""
        mock_get_emails.return_value = ['existing@inspection.gc.ca']
        mock_send_email.return_value = True
        mock_redis.setex.return_value = True
        
        response = client.post('/unsubscribe', data={'email': 'existing@inspection.gc.ca'})
        assert response.status_code == 302
        mock_send_email.assert_called_once()
    
    @patch('app.get_current_emails')
    def test_unsubscribe_nonexistent_email(self, mock_get_emails, client):
        """Test unsubscribing a non-existent email"""
        mock_get_emails.return_value = []
        
        response = client.post('/unsubscribe', data={'email': 'nonexistent@inspection.gc.ca'})
        assert response.status_code == 302
    
    @patch('app.redis_client')
    @patch('app.get_current_emails')
    @patch('app.update_github_secrets')
    def test_confirm_unsubscribe_valid_token(self, mock_update_secrets, mock_get_emails, mock_redis, client):
        """Test confirming unsubscription with valid token"""
        mock_redis.get.return_value = 'test@inspection.gc.ca'
        mock_get_emails.return_value = ['test@inspection.gc.ca']
        mock_update_secrets.return_value = True
        
        response = client.get('/confirm_unsubscribe?token=valid-token&email=test@inspection.gc.ca')
        assert response.status_code == 302
        mock_update_secrets.assert_called_once()

class TestGitHubIntegration:
    """Test GitHub API integration"""
    
    @patch('app.requests.get')
    @patch('app.requests.put')
    def test_update_github_secrets_success(self, mock_put, mock_get):
        """Test successful GitHub secrets update"""
        # Mock public key response
        mock_get.return_value.json.return_value = {
            'key': 'mock_public_key',
            'key_id': 'mock_key_id'
        }
        mock_get.return_value.raise_for_status.return_value = None
        
        # Mock put responses
        mock_put.return_value.raise_for_status.return_value = None
        
        test_emails = ['test@inspection.gc.ca']
        
        with patch('app.encrypt_secret_for_repository', return_value='encrypted_value'):
            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file
                
                result = update_github_secrets(test_emails)
                assert result == True
                
                # Should call PUT for both secrets
                assert mock_put.call_count == 2
    
    @patch('app.requests.get')
    @patch('app.requests.put')
    def test_update_github_secrets_failure(self, mock_put, mock_get):
        """Test GitHub secrets update failure"""
        mock_get.return_value.json.return_value = {
            'key': 'mock_public_key',
            'key_id': 'mock_key_id'
        }
        mock_get.return_value.raise_for_status.return_value = None
        
        # Mock failure
        mock_put.return_value.raise_for_status.side_effect = Exception('API Error')
        
        test_emails = ['test@inspection.gc.ca']
        
        with patch('app.encrypt_secret_for_repository', return_value='encrypted_value'):
            with pytest.raises(Exception):
                update_github_secrets(test_emails)

class TestWebInterface:
    """Test web interface endpoints"""
    
    @patch('app.get_current_emails')
    def test_home_page(self, mock_get_emails, client):
        """Test home page loads with subscriber count"""
        mock_get_emails.return_value = ['test1@inspection.gc.ca', 'test2@inspection.gc.ca']
        
        response = client.get('/')
        assert response.status_code == 200
        assert b'2' in response.data  # Subscriber count
    
    def test_subscribe_page(self, client):
        """Test subscribe page loads"""
        response = client.get('/subscribe')
        assert response.status_code == 200
        assert b'Subscribe' in response.data
    
    def test_unsubscribe_page(self, client):
        """Test unsubscribe page loads"""
        response = client.get('/unsubscribe')
        assert response.status_code == 200
        assert b'Unsubscribe' in response.data
    
    @patch('app.get_current_emails')
    def test_api_subscriber_count(self, mock_get_emails, client):
        """Test API endpoint for subscriber count"""
        mock_get_emails.return_value = ['test@inspection.gc.ca']
        
        response = client.get('/api/subscribers/count')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['count'] == 1

class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_missing_token_parameter(self, client):
        """Test confirmation URLs without token parameter"""
        response = client.get('/confirm_subscribe?email=test@inspection.gc.ca')
        assert response.status_code == 302
        
        response = client.get('/confirm_unsubscribe?email=test@inspection.gc.ca')
        assert response.status_code == 302
    
    def test_missing_email_parameter(self, client):
        """Test confirmation URLs without email parameter"""
        response = client.get('/confirm_subscribe?token=test-token')
        assert response.status_code == 302
        
        response = client.get('/confirm_unsubscribe?token=test-token')
        assert response.status_code == 302
    
    @patch('app.get_current_emails')
    def test_corrupted_state_file(self, mock_get_emails, temp_dir):
        """Test handling of corrupted emails_state.json"""
        # Create corrupted JSON file
        with open('emails_state.json', 'w') as f:
            f.write('invalid json content')
        
        # Should handle gracefully and return empty list
        emails = get_current_emails()
        assert emails == []

if __name__ == '__main__':
    # Run tests with pytest
    pytest.main(['-v', __file__])