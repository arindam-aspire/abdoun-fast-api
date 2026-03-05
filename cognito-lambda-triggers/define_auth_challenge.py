"""
Cognito "Define Auth Challenge" Lambda trigger (Python).
Use this in the AWS Lambda console for function: cognito-define-auth-challenge
Runtime: Python 3.11 or 3.12
Handler: define_auth_challenge.handler
See: docs/COGNITO_OTP_LAMBDA_SETUP.md
"""


def handler(event, context):
    session = event["request"].get("session", [])

    if len(session) == 0:
        event["response"]["challengeName"] = "CUSTOM_CHALLENGE"
        event["response"]["issueTokens"] = False
        event["response"]["failAuthentication"] = False
        return event

    last = session[-1]
    if last.get("challengeName") == "CUSTOM_CHALLENGE" and last.get("challengeResult") is True:
        event["response"]["challengeName"] = None
        event["response"]["issueTokens"] = True
        event["response"]["failAuthentication"] = False
        return event

    if len(session) >= 3:
        event["response"]["challengeName"] = None
        event["response"]["issueTokens"] = False
        event["response"]["failAuthentication"] = True
        return event

    event["response"]["challengeName"] = "CUSTOM_CHALLENGE"
    event["response"]["issueTokens"] = False
    event["response"]["failAuthentication"] = False
    return event
