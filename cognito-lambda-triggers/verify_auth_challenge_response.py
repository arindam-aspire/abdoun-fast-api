"""
Cognito "Verify Auth Challenge Response" Lambda trigger (Python).
Use this in the AWS Lambda console for function: cognito-verify-auth-challenge
Runtime: Python 3.11 or 3.12
Handler: verify_auth_challenge_response.handler
See: docs/COGNITO_OTP_LAMBDA_SETUP.md
"""


def handler(event, context):
    private = event["request"].get("privateChallengeParameters") or {}
    expected = private.get("answer")
    user_answer = (event["request"].get("challengeAnswer") or "").strip()

    event["response"]["answerCorrect"] = expected == user_answer
    return event
