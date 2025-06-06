import json
import os
import boto3
import base64
import hmac
import hashlib
from boto3.dynamodb.conditions import Key

# 🔐 Env vars
SECRET = os.environ.get('JWT_SECRET', 'default-secret')
TABLE_USERS = os.environ.get('TABLE_USERS', 'Users')
TABLE_SKILLS = os.environ.get('TABLE_SKILLS', 'Skills')
TABLE_SUBMISSIONS = os.environ.get('TABLE_SUBMISSIONS', 'Submissions')
TABLE_ACTIVITIES = os.environ.get('TABLE_ACTIVITIES', 'Activities')

# 🔗 DynamoDB
ddb = boto3.resource('dynamodb')
users_table = ddb.Table(TABLE_USERS)
skills_table = ddb.Table(TABLE_SKILLS)
subs_table = ddb.Table(TABLE_SUBMISSIONS)
acts_table = ddb.Table(TABLE_ACTIVITIES)

# 🌐 CORS headers
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,OPTIONS"
}

# 🔐 JWT decode
def decode_jwt(token, secret):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature_b64 = parts
        msg = f"{header_b64}.{payload_b64}".encode()
        signature = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
        expected_sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        if not hmac.compare_digest(expected_sig, signature_b64.rstrip("=")):
            return None
        padded_payload = payload_b64 + '=' * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded_payload).decode())
    except Exception as e:
        print("JWT decode error:", e)
        return None

# 🚀 Main handler
def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "CORS preflight success"})
        }

    token = event.get('headers', {}).get('Authorization') or event.get('headers', {}).get('authorization')
    if not token or not token.startswith('Bearer '):
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing or invalid token"})}

    user = decode_jwt(token.replace('Bearer ', ''), SECRET)
    if not user or user.get('role') != 'advisor':
        return {"statusCode": 403, "headers": CORS_HEADERS, "body": json.dumps({"message": "Access denied"})}

    params = event.get('queryStringParameters') or {}
    student_id = params.get('studentId')
    if not student_id:
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing studentId"})}

    try:
        # ✅ Get student name from Users table
        try:
            user_item = users_table.get_item(Key={'userId': student_id}).get('Item', {})
            name = user_item.get('name', student_id)
        except Exception as err:
            print("Name lookup failed:", err)
            name = student_id

        # 🧠 Skill split
        soft, hard = [], []
        response = skills_table.query(
            IndexName='userId-index',
            KeyConditionExpression=Key('userId').eq(student_id)
        )
        for item in response.get('Items', []):
            skill = item.get('skillName')
            if skill in ["Teamwork", "Communication", "Leadership", "Problem-solving", "Humility", "Adaptability", "Creativity", "Innovation"]:
                soft.append(skill)
            else:
                hard.append(skill)

        # 📝 Submissions + activity info
        result = subs_table.query(
            IndexName='userId-index',
            KeyConditionExpression=Key('userId').eq(student_id)
        )
        activities = []
        for s in result.get('Items', []):
            act_id = s['activityId']
            act_info = acts_table.get_item(Key={'activityId': act_id}).get('Item', {})
            skills_json = s.get('skills', '[]')
            try:
                parsed_skills = json.loads(skills_json)
            except:
                parsed_skills = []

            activities.append({
                "activityId": act_id,
                "name": act_info.get('name', ''),
                "score": int(s.get('score', 0)),
                "total": int(s.get('total', 10)),
                "skills": parsed_skills,
                "proofUrl": s.get('proofUrl', '')
            })

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "studentId": student_id,
                "name": name,
                "totalActivities": len(activities),
                "softSkills": soft,
                "hardSkills": hard,
                "activities": activities
            }, ensure_ascii=False, default=str)
        }

    except Exception as e:
        print("ERROR in /student-summary:", str(e))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Failed to get student summary", "error": str(e)})
        }
