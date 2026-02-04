import boto3
import json
import os
import logging

# =====================================================
# 基本設定
# =====================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

BINDER_ENV = os.environ["BINDER_ENV"]
BUCKET_PREFIX = os.environ["BUCKET_PREFIX"]
EXPIRE_PUT = int(os.environ["EXPIRE_PUT"])
EXPIRE_GET = int(os.environ["EXPIRE_GET"])


# =====================================================
# 共通ユーティリティ
# =====================================================

def extract_cn(subject_dn: str) -> str:
    """
    SubjectDN から CN を抽出
    例: 'CN=client001,O=example' → 'client001'
    """
    for part in subject_dn.split(","):
        part = part.strip()
        if part.startswith("CN="):
            return part[3:]
    raise ValueError("CN not found in subject DN")


def get_client_cn(event) -> str:
    """
    API Gateway (HTTP API + mTLS) から
    クライアント証明書 CN を取得
    """
    try:
        auth = event["requestContext"]["authentication"]
        cert = auth.get("clientCert") or auth.get("mtls")
        subject_dn = cert["subjectDN"]
        return extract_cn(subject_dn)
    except Exception as e:
        logger.error(f"Failed to get client CN: {e}")
        raise ValueError("Client certificate not found")


def resolve_bucket_name(cn: str) -> str:
    """
    CN + 環境から S3 バケット名を決定
    """
    return f"{BUCKET_PREFIX}-{BINDER_ENV}-{cn}"


def response(status: int, body: dict):
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
        rc = event["requestContext"]["http"]
        method = rc["method"]

        params = event.get("pathParameters") or {}
        key = params.get("filename")

        cn = get_client_cn(event)
        bucket = resolve_bucket_name(cn)

        logger.info(f"method={method}, bucket={bucket}, key={key}")

        # -------------------------------
        # PUT (Upload)
        # -------------------------------
        if method == "PUT" and key:
            url = s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=EXPIRE_PUT
            )
            return response(200, {
                "operation": "put",
                "bucket": bucket,
                "key": key,
                "url": url
            })

        # -------------------------------
        # GET (Download)
        # -------------------------------
        if method == "GET" and key:
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=EXPIRE_GET
            )
            return response(200, {
                "operation": "get",
                "bucket": bucket,
                "key": key,
                "url": url
            })

        # -------------------------------
        # DELETE
        # -------------------------------
        if method == "DELETE" and key:
            url = s3.generate_presigned_url(
                "delete_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=EXPIRE_GET
            )
            return response(200, {
                "operation": "delete",
                "bucket": bucket,
                "key": key,
                "url": url
            })

        # -------------------------------
        # LIST（必須）
        # GET /objects
        # -------------------------------
        if method == "GET" and not key:
            resp = s3.list_objects_v2(Bucket=bucket)
            keys = [obj["Key"] for obj in resp.get("Contents", [])]

            return response(200, {
                "operation": "list",
                "bucket": bucket,
                "keys": keys
            })

        return response(400, {"message": "Invalid request"})

    except ValueError as e:
        return response(401, {"message": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return response(500, {"message": "Internal server error"})
