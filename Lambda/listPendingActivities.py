import json
import os
import base64
import hmac
import hashlib
import boto3

# ENV
SECRET = os.environ.get('JWT_SECRET', 'default-secret')
TABLE = os.environ.get('TABLE_ACTIVITIES', 'Activities')
STATUS_INDEX = 'status-index'

dynamodb = boto3.client('dynamodb')

def decode_jwt(token, secret):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature_b64 = parts
        msg = f"{header_b64}.{payload_b64}".encode()
        sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b'=').decode()
        if sig_b64 != signature_b64:
            return None
        payload_json = base64.urlsafe_b64decode(payload_b64 + '==')
        payload = json.loads(payload_json.decode())
        return payload
    except:
        return None

def lambda_handler(event, context):
    headers = event.get('headers', {})
    token = headers.get('Authorization') or headers.get('authorization')
    if not token or not token.startswith('Bearer '):
        return {"statusCode": 401, "body": json.dumps({"message": "Missing or invalid token"})}

    token = token.replace('Bearer ', '')
    user = decode_jwt(token, SECRET)
    if not user or user.get('role') != 'admin':
        return {"statusCode": 403, "body": json.dumps({"message": "Only admin can view pending activities"})}

    try:
        result = dynamodb.query(
            TableName=TABLE,
            IndexName=STATUS_INDEX,
            KeyConditionExpression="#s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": {"S": "pending"}}
        )

        items = [
            {k: list(v.values())[0] for k, v in item.items()}
            for item in result.get('Items', [])
        ]

        return {
            "statusCode": 200,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps(items)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Failed to list pending activities", "error": str(e)})
        }
