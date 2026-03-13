import hmac
import hashlib
import base64
import secrets
import boto3
import requests
from jose import jwt
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
from typing import Optional, Dict, Any, List

from app.core.config import get_settings
from app.utils.logger import api_logger
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.constants import ErrorMessages

settings = get_settings()

class CognitoService:
    def __init__(self):
        # Initialize boto3 client with credentials if provided, otherwise use default credential chain
        client_kwargs = {"region_name": settings.cognito_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            client_kwargs.update({
                "aws_access_key_id": settings.aws_access_key_id,
                "aws_secret_access_key": settings.aws_secret_access_key
            })
        
        self.client = boto3.client("cognito-idp", **client_kwargs)
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

    def create_agent_user(self, email: str, full_name: str, phone_number: str) -> Dict[str, Any]:
        """
        Create a Cognito user for an agent without a password (OTP-only authentication).
        
        This is used when an admin approves an agent during the onboarding flow. The user is created with:
        - No password (agents login via OTP)
        - Email and phone verified
        - MessageAction="SUPPRESS" to prevent Cognito from sending welcome emails
        
        Note: This uses admin_create_user which requires AWS credentials with admin permissions.
        Unlike sign_up() which is a public API, this requires proper AWS IAM credentials.
        
        Args:
            email: Agent's email address
            full_name: Agent's full name
            phone_number: Agent's phone number in E.164 format
            
        Returns:
            Dict containing Cognito user creation response with "User" key containing "Username" (cognito_sub)
            
        Raises:
            ClientError: If Cognito API call fails (except NoCredentialsError which is handled gracefully)
            NoCredentialsError: If AWS credentials are not configured (allows agent approval to proceed)
        """
        try:
            # Verify we have the required configuration
            if not self.user_pool_id or not self.user_pool_id.strip():
                raise ValueError("COGNITO_USER_POOL_ID is not configured")
            
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
        except NoCredentialsError as e:
            # AWS credentials not configured - allow agent approval to proceed
            api_logger.warning(
                format_log_message(
                    LogMessages.Auth.SIGNUP_FAILED,
                    email=email,
                    error=f"AWS credentials not configured: {str(e)}"
                ) + " - Agent approval will proceed but Cognito user not created. Note: admin_create_user requires AWS credentials, unlike sign_up() which is a public API."
            )
            raise e  # Re-raise to allow caller to handle gracefully
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "") if hasattr(e, 'response') else ""
            if error_code == "UsernameExistsException":
                # User already exists in Cognito - this is okay, we can still proceed
                api_logger.warning(
                    format_log_message(
                        LogMessages.Auth.SIGNUP_FAILED,
                        email=email,
                        error=f"User already exists in Cognito: {str(e)}"
                    ) + " - This is expected if user was created via signup. Agent approval will proceed."
                )
                # Try to get the existing user's username (sub)
                try:
                    user_info = self.client.admin_get_user(
                        UserPoolId=self.user_pool_id,
                        Username=email
                    )
                    # Return a response in the expected format
                    return {
                        "User": {
                            "Username": user_info.get("Username", email)
                        }
                    }
                except Exception:
                    # If we can't get user info, still raise the original error
                    raise e
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
        except (ClientError, NoCredentialsError, BotoCoreError) as e:
            api_logger.warning(format_log_message(LogMessages.Auth.TOKEN_VERIFICATION_FAILED, error=str(e)))
            return None
        except Exception as e:
            # Catch any other unexpected exceptions
            api_logger.warning(format_log_message(LogMessages.Auth.TOKEN_VERIFICATION_FAILED, error=str(e)))
            return None

    def admin_confirm_user(self, email: str):
        """Confirm a user account manually by setting a random permanent password (user must reset)."""
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

    def admin_confirm_sign_up(self, username: str) -> bool:
        """
        Confirm a user's sign-up as admin without changing their password.
        Use this after sign_up() so the user can log in with the same password.
        """
        try:
            self.client.admin_confirm_sign_up(
                UserPoolId=self.user_pool_id,
                Username=username,
            )
            return True
        except ClientError as e:
            api_logger.error(
                format_log_message(LogMessages.Auth.ADMIN_CONFIRM_FAILED, email=username, error=str(e))
            )
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
            error_code = e.response.get("Error", {}).get("Code", "")
            error_msg = str(e).lower()
            # Token already revoked (e.g. double logout) → treat as success
            if error_code == "NotAuthorizedException" and "revoked" in error_msg:
                api_logger.info(LogMessages.Auth.LOGOUT_SUCCESS_GENERIC)
                return True
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

    def change_password(self, access_token: str, previous_password: str, proposed_password: str) -> bool:
        """
        Change password for an authenticated user.
        
        Args:
            access_token: The user's current access token (from Bearer header)
            previous_password: Current password (can be empty string for users without password)
            proposed_password: New password to set
            
        Returns:
            bool: True if password change successful
            
        Raises:
            ClientError: If Cognito API call fails
        """
        try:
            # For users without a password (created via create_agent_user), previous_password can be empty
            # Cognito's change_password requires previous_password, but for users without password,
            # we need to use admin_set_user_password instead
            # However, change_password works if the user has logged in via OTP and has a session
            
            # Try change_password first (for users who have a password)
            if previous_password:
                self.client.change_password(
                    PreviousPassword=previous_password,
                    ProposedPassword=proposed_password,
                    AccessToken=access_token
                )
            else:
                # For users without password, use admin_set_user_password
                try:
                    # Verify token signature before extracting username/sub
                    payload = self.verify_token(access_token)
                    if not payload:
                        raise ValueError("Token verification failed")
                    # The 'sub' field in the token is the Cognito username
                    username = payload.get("sub") or payload.get("username")
                    
                    if not username:
                        raise ValueError("Cannot extract username from access token")
                    
                    self.client.admin_set_user_password(
                        UserPoolId=self.user_pool_id,
                        Username=username,
                        Password=proposed_password,
                        Permanent=True
                    )
                except (ValueError, KeyError, Exception) as decode_error:
                    api_logger.error(f"Failed to extract username from token: {str(decode_error)}")
                    raise ClientError(
                        {"Error": {"Code": "InvalidParameterException", "Message": f"Cannot extract username from token: {str(decode_error)}"}},
                        "change_password"
                    )
            
            api_logger.info(format_log_message(LogMessages.Auth.PASSWORD_RESET_SUCCESS, email="user"))
            return True
        except ClientError as e:
            api_logger.error(format_log_message(LogMessages.Auth.PASSWORD_RESET_FAILED, email="user", error=str(e)))
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
