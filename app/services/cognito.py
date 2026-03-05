import hmac
import hashlib
import base64
import secrets
import boto3
import requests
from jose import jwt
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any, List

from app.core.config import get_settings
from app.utils.logger import api_logger
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.constants import ErrorMessages

settings = get_settings()

class CognitoService:
    def __init__(self):
        self.client = boto3.client("cognito-idp", region_name=settings.cognito_region)
        self.user_pool_id = settings.cognito_user_pool_id
        self.client_id = settings.cognito_client_id
        self.client_secret = settings.cognito_client_secret
        self._jwks_cache = None
        self._jwks_last_fetch = None

    def _get_secret_hash(self, username: str) -> Optional[str]:
        """Compute the SECRET_HASH required when the App Client has a client secret."""
        if not self.client_secret:
            return None
        message = username + self.client_id
        dig = hmac.new(
            self.client_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(dig).decode()

    def signup(self, email: str, password: str, full_name: str, phone_number: str) -> Dict[str, Any]:
        try:
            kwargs: Dict[str, Any] = {
                "ClientId": self.client_id,
                "Username": email,
                "Password": password,
                "UserAttributes": [
                    {"Name": "email", "Value": email},
                    {"Name": "name", "Value": full_name},
                    {"Name": "phone_number", "Value": phone_number},
                ],
            }
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                kwargs["SecretHash"] = secret_hash
            response = self.client.sign_up(**kwargs)
            api_logger.info(format_log_message(LogMessages.Auth.SIGNUP_SUCCESS, email=email))
            return response
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.SIGNUP_FAILED, email=email, error=str(e)))
            raise e

    def admin_create_user(self, email: str, full_name: str, phone_number: str) -> Dict[str, Any]:
        """Create a user with AdminPrivileges, useful for OTP-only users or pre-registering agents."""
        try:
            response = self.client.admin_create_user(
                UserPoolId=self.user_pool_id,
                Username=email,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "name", "Value": full_name},
                    {"Name": "phone_number", "Value": phone_number},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "phone_number_verified", "Value": "true"},
                ],
                MessageAction="SUPPRESS", # We handle notifications ourselves
            )
            api_logger.info(format_log_message(LogMessages.Auth.SIGNUP_SUCCESS, email=email))
            return response
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.SIGNUP_FAILED, email=email, error=str(e)))
            raise e
            
    def get_user_attributes_by_sub(self, cognito_sub: str) -> Optional[Dict[str, str]]:
        """Get Cognito user attributes (e.g. email) by sub. Use when access token has sub but no email."""
        try:
            response = self.client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=cognito_sub,
            )
            attrs = {a["Name"]: a["Value"] for a in response.get("UserAttributes", [])}
            return attrs
        except ClientError as e:
            api_logger.warning(format_log_message(LogMessages.Auth.TOKEN_VERIFICATION_FAILED, error=str(e)))
            return None

    def admin_confirm_user(self, email: str):
        """Confirm a user account manually."""
        try:
            self.client.admin_set_user_password(
                UserPoolId=self.user_pool_id,
                Username=email,
                Password=secrets.token_urlsafe(16) + "1aA!", # Random temporary password
                Permanent=True
            )
            return True
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.ADMIN_CONFIRM_FAILED, email=email, error=str(e)))
            raise e

    def login_password(self, email: str, password: str) -> Dict[str, Any]:
        try:
            auth_params: Dict[str, str] = {
                "USERNAME": email,
                "PASSWORD": password,
            }
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                auth_params["SECRET_HASH"] = secret_hash
            response = self.client.initiate_auth(
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters=auth_params,
                ClientId=self.client_id,
            )
            api_logger.info(format_log_message(LogMessages.Auth.LOGIN_SUCCESS, email=email))
            return response["AuthenticationResult"]
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.LOGIN_FAILED, email=email, error=str(e)))
            raise e

    def login_otp_request(self, username: str) -> Dict[str, Any]:
        try:
            auth_params: Dict[str, str] = {
                "USERNAME": username,
            }
            secret_hash = self._get_secret_hash(username)
            if secret_hash:
                auth_params["SECRET_HASH"] = secret_hash
            response = self.client.initiate_auth(
                AuthFlow="CUSTOM_AUTH",
                AuthParameters=auth_params,
                ClientId=self.client_id,
            )
            api_logger.info(format_log_message(LogMessages.Auth.OTP_REQUEST_SUCCESS, username=username))
            return response
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.OTP_REQUEST_FAILED, username=username, error=str(e)))
            raise e

    def login_otp_verify(self, session: str, username: str, code: str) -> Dict[str, Any]:
        try:
            challenge_responses: Dict[str, str] = {
                "USERNAME": username,
                "ANSWER": code,
            }
            secret_hash = self._get_secret_hash(username)
            if secret_hash:
                challenge_responses["SECRET_HASH"] = secret_hash
            response = self.client.respond_to_auth_challenge(
                ClientId=self.client_id,
                ChallengeName="CUSTOM_CHALLENGE",
                Session=session,
                ChallengeResponses=challenge_responses,
            )
            api_logger.info(format_log_message(LogMessages.Auth.LOGIN_SUCCESS, email=username))
            return response["AuthenticationResult"]
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.LOGIN_FAILED, email=username, error=str(e)))
            raise e

    def refresh_token(self, refresh_token: str, username: str = "") -> Dict[str, Any]:
        try:
            auth_params: Dict[str, str] = {
                "REFRESH_TOKEN": refresh_token,
            }
            # SECRET_HASH for refresh uses the username (sub or email) if provided
            secret_hash = self._get_secret_hash(username) if username else None
            if secret_hash:
                auth_params["SECRET_HASH"] = secret_hash
            response = self.client.initiate_auth(
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters=auth_params,
                ClientId=self.client_id,
            )
            api_logger.info(LogMessages.Auth.TOKEN_REFRESH_SUCCESS)
            return response["AuthenticationResult"]
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.TOKEN_REFRESH_FAILED, error=str(e)))
            raise e

    def logout(self, access_token: str):
        try:
            self.client.global_sign_out(AccessToken=access_token)
            api_logger.info(LogMessages.Auth.LOGOUT_SUCCESS_GENERIC)
            return True
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.LOGOUT_FAILED, error=str(e)))
            raise e

    def forgot_password_request(self, email: str):
        try:
            kwargs: Dict[str, Any] = {
                "ClientId": self.client_id,
                "Username": email,
            }
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                kwargs["SecretHash"] = secret_hash
            self.client.forgot_password(**kwargs)
            api_logger.info(format_log_message(LogMessages.Auth.PASSWORD_RESET_REQUEST, email=email))
            return True
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.PASSWORD_RESET_FAILED, email=email, error=str(e)))
            raise e

    def confirm_signup(self, email: str, code: str) -> bool:
        try:
            kwargs: Dict[str, Any] = {
                "ClientId": self.client_id,
                "Username": email,
                "ConfirmationCode": code,
            }
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                kwargs["SecretHash"] = secret_hash
            self.client.confirm_sign_up(**kwargs)
            return True
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.SIGNUP_FAILED, email=email, error=str(e)))
            raise e

    def resend_confirmation_code(self, email: str) -> bool:
        try:
            kwargs: Dict[str, Any] = {
                "ClientId": self.client_id,
                "Username": email,
            }
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                kwargs["SecretHash"] = secret_hash
            self.client.resend_confirmation_code(**kwargs)
            return True
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.SIGNUP_FAILED, email=email, error=str(e)))
            raise e

    def forgot_password_confirm(self, email: str, code: str, new_password: str):
        try:
            kwargs: Dict[str, Any] = {
                "ClientId": self.client_id,
                "Username": email,
                "ConfirmationCode": code,
                "Password": new_password,
            }
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                kwargs["SecretHash"] = secret_hash
            self.client.confirm_forgot_password(**kwargs)
            api_logger.info(format_log_message(LogMessages.Auth.PASSWORD_RESET_SUCCESS, email=email))
            return True
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.PASSWORD_RESET_FAILED, email=email, error=str(e)))
            raise e

    def get_social_login_url(self, provider: str) -> str:
        """
        Generate the Cognito Hosted UI URL for a given provider (e.g., Google, Apple).
        """
        base_url = f"https://{settings.cognito_domain}/oauth2/authorize"
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": settings.social_redirect_uri,
            "identity_provider": provider,
            "scope": "email openid profile"
        }
        query_str = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_url}?{query_str}"

    def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange OAuth2 authorization code for tokens.
        """
        token_url = f"https://{settings.cognito_domain}/oauth2/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": settings.social_redirect_uri,
        }
        try:
            response = requests.post(token_url, data=data, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            api_logger.error(format_log_message(LogMessages.Auth.SOCIAL_AUTH_FAILED_LOG, email=LogMessages.Auth.UNKNOWN_EMAIL, error=str(e)))
            raise e

    def _get_jwks(self) -> List[Dict[str, Any]]:
        import time
        # Cache JWKS for 24 hours
        if self._jwks_cache and self._jwks_last_fetch and (time.time() - self._jwks_last_fetch < 86400):
            return self._jwks_cache

        jwks_url = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json"
        try:
            response = requests.get(jwks_url, timeout=5)
            response.raise_for_status()
            self._jwks_cache = response.json()["keys"]
            self._jwks_last_fetch = time.time()
            return self._jwks_cache
        except Exception as e:
            api_logger.error(format_log_message(LogMessages.Auth.JWKS_FETCH_FAILED, error=str(e)))
            return self._jwks_cache or [] # Return stale cache if fetch fails

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            headers = jwt.get_unverified_header(token)
            kid = headers["kid"]
            
            jwks = self._get_jwks()
            key = next((k for k in jwks if k["kid"] == kid), None)
            
            if not key:
                api_logger.warning(format_log_message(LogMessages.Auth.JWKS_KEY_NOT_FOUND, kid=kid))
                return None
                
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{self.user_pool_id}"
            )
            return payload
        except Exception as e:
            api_logger.error(format_log_message(LogMessages.Auth.TOKEN_VERIFICATION_FAILED, error=str(e)))
            return None

cognito_service = CognitoService()
