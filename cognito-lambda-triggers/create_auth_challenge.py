"""
Cognito "Create Auth Challenge" Lambda trigger (Python).
Use this in the AWS Lambda console for function: cognito-create-auth-challenge
Runtime: Python 3.11 or 3.12
Handler: create_auth_challenge.handler

Supports sending OTP by:
- Email (SES): set SES_FROM_EMAIL to a verified sender; attach ses:SendEmail to Lambda role.
- SMS (SNS): set ENABLE_SMS_OTP=true; attach sns:Publish to Lambda role. Phone from userAttributes.phone_number (E.164).

See: docs/COGNITO_OTP_LAMBDA_SETUP.md and docs/OTP_SMS_SETUP.md
"""
import os
import re
import secrets
import string

import boto3
from botocore.exceptions import ClientError

FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "YOUR_VERIFIED_EMAIL")
SKIP_SES_FOR_TESTING = os.environ.get("SKIP_SES_FOR_TESTING", "").lower() in ("1", "true", "yes")
# Set to true to send OTP via SMS when user has phone_number (E.164). Requires SNS publish permission.
ENABLE_SMS_OTP = os.environ.get("ENABLE_SMS_OTP", "").lower() in ("1", "true", "yes")
# When both email and SMS are possible: "sms" = prefer SMS, "email" = prefer email
OTP_CHANNEL_PREFERENCE = (os.environ.get("OTP_CHANNEL_PREFERENCE", "sms") or "sms").lower()

ses = boto3.client("ses")
sns = boto3.client("sns")

# E.164: + and 10–15 digits
E164_REGEX = re.compile(r"^\+[1-9]\d{9,14}$")


def random_digits(length: int) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def is_valid_e164(phone: str) -> bool:
    return bool(phone and E164_REGEX.match(phone.strip()))


def send_otp_email(email: str, otp: str) -> bool:
    if not FROM_EMAIL or FROM_EMAIL == "YOUR_VERIFIED_EMAIL":
        print("SES skipped: SES_FROM_EMAIL is missing or still placeholder value")
        return False
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": "Your login code"},
                "Body": {
                    "Text": {
                        "Data": f"Your one-time login code is: {otp}. It expires in a few minutes."
                    }
                },
            },
        )
        return True
    except ClientError as e:
        err = e.response.get("Error", {}) if hasattr(e, "response") else {}
        code = err.get("Code", "Unknown")
        message = err.get("Message", str(e))
        print(
            "SES send failed | "
            f"code={code} message={message} "
            f"from={FROM_EMAIL} to={email} region={os.environ.get('AWS_REGION', 'unknown')}"
        )
        return False
    except Exception as e:
        print(
            "SES send failed | "
            f"unexpected_error={e} from={FROM_EMAIL} to={email} "
            f"region={os.environ.get('AWS_REGION', 'unknown')}"
        )
        return False


def send_otp_sms(phone: str, otp: str) -> bool:
    if not ENABLE_SMS_OTP or not is_valid_e164(phone):
        return False
    try:
        sns.publish(
            PhoneNumber=phone.strip(),
            Message=f"Your login code is: {otp}. It expires in a few minutes.",
        )
        return True
    except Exception as e:
        print(f"SNS send failed: {e}")
        return False


def handler(event, context):
    if event["request"].get("challengeName") != "CUSTOM_CHALLENGE":
        return event

    otp = random_digits(6)
    user_attrs = event["request"].get("userAttributes", {})
    email = (user_attrs.get("email") or "").strip()
    phone = (user_attrs.get("phone_number") or "").strip()

    if not email and not phone:
        print("No email or phone_number in userAttributes")
        return event

    event["response"]["privateChallengeParameters"] = {"answer": otp}
    event["response"]["publicChallengeParameters"] = {}
    event["response"]["challengeMetadata"] = "OTP_CHALLENGE"

    sent = False

    # Prefer SMS when enabled and phone is valid; else prefer email
    use_sms = ENABLE_SMS_OTP and is_valid_e164(phone)
    use_email = bool(email)

    if OTP_CHANNEL_PREFERENCE == "sms" and use_sms:
        sent = send_otp_sms(phone, otp)
        if sent:
            print(f"OTP sent via SMS to {phone[:6]}***")
    if not sent and use_email:
        if not SKIP_SES_FOR_TESTING:
            sent = send_otp_email(email, otp)
        if not sent:
            print(f"[OTP for testing] email={email} code={otp}")
    if not sent and use_sms and OTP_CHANNEL_PREFERENCE != "sms":
        sent = send_otp_sms(phone, otp)
        if sent:
            print(f"OTP sent via SMS to {phone[:6]}***")
    if not sent and use_email and OTP_CHANNEL_PREFERENCE == "sms":
        if not SKIP_SES_FOR_TESTING:
            sent = send_otp_email(email, otp)
        if not sent:
            print(f"[OTP for testing] email={email} code={otp}")

    return event
