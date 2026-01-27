import boto3
import json
import os
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

PRESIGN_EXPIRE = int(os.environ.get("PRESIGN_EXPIRE", "3600"))

# =====================================================
# 共通処理
# =====================================================

def extract_cn(subject_dn: str) -> str:
    for part in subject_dn.split(","):
        part = part.strip()
        if part.startswith("CN="):
            return part.replace("CN=", "")
    raise ValueError("CN not found in subject DN")


def get_client_cn(event) -> str:
    try:
        subject_dn = (
            event["requestContext"]
            ["authentication"]
            ["clientCert"]
            ["subjectDN"]
        )
    except KeyError:
        raise ValueError("Client certificate information not found")

    return extract_cn(subject_dn)


def resolve_bucket_name(cn: str) -> str:
    return f"binder-{cn}"


def ensure_bucket_exists(bucket: str):
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            raise ValueError("Bucket not found")
        raise


def json_response(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }


# =====================================================
# メインハンドラ
# =====================================================

def lambda_handler(event, context):
    try:
        method = event["requestContext"]["http"]["method"]
        path = event["requestContext"]["http"]["path"]
        query = event.get("queryStringParameters") or {}

        # クライアント識別
        cn = get_client_cn(event)
        bucket = resolve_bucket_name(cn)
        ensure_bucket_exists(bucket)

        key = query.get("key")

        # -------------------------------------------------
        # PUT
        # -------------------------------------------------
        if method == "POST" and path == "/presign/put":
            if not key:
                return json_response(400, {"message": "key is required"})

            url = s3.generate_presigned_url(
                ClientMethod="put_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=PRESIGN_EXPIRE
            )

            return json_response(200, {
                "operation": "put",
                "bucket": bucket,
                "key": key,
                "url": url
            })

        # -------------------------------------------------
        # GET
        # -------------------------------------------------
        if method == "POST" and path == "/presign/get":
            if not key:
                return json_response(400, {"message": "key is required"})

            url = s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=PRESIGN_EXPIRE
            )

            return json_response(200, {
                "operation": "get",
                "bucket": bucket,
                "key": key,
                "url": url
            })

        # -------------------------------------------------
        # DELETE
        # -------------------------------------------------
        if method == "POST" and path == "/presign/delete":
            if not key:
                return json_response(400, {"message": "key is required"})

            url = s3.generate_presigned_url(
                ClientMethod="delete_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=PRESIGN_EXPIRE
            )

            return json_response(200, {
                "operation": "delete",
                "bucket": bucket,
                "key": key,
                "url": url
            })

        # -------------------------------------------------
        # LIST（Lambda直実行）
        # -------------------------------------------------
        if method == "POST" and path == "/presign/list":
            resp = s3.list_objects_v2(Bucket=bucket)
            keys = [obj["Key"] for obj in resp.get("Contents", [])]

            return json_response(200, {
                "operation": "list",
                "bucket": bucket,
                "keys": keys
            })

        return json_response(400, {"message": "Invalid request"})

    except ValueError as e:
        return json_response(401, {"message": str(e)})
    except Exception:
        return json_response(500, {"message": "Internal server error"})
