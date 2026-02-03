import boto3, json, os


s3 = boto3.client("s3")

def extract_cn(subject_dn: str) -> str:
    for part in subject_dn.split(","):
        part = part.strip()
        if part.startswith("CN="):
            return part.replace("CN=", "")
    raise ValueError("CN not found in subjectDN")

def get_subject_dn(event) -> str:
    rc = event.get("requestContext", {})
    auth = rc.get("authentication", {})
    mtls = auth.get("mtls", {})
    client_cert = mtls.get("clientCert") or auth.get("clientCert") or {}
    subject = client_cert.get("subjectDN")
    if subject:
        return subject
    raise ValueError("Client certificate not found")

def bucket_from_event(event) -> str:
    env = os.environ.get("BINDER_ENV")
    prefix = os.environ.get("BUCKET_PREFIX")
    cn = extract_cn(get_subject_dn(event))
    return f"{prefix}-{env}-{cn}"

def response(code, body):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }

def handler(event, context):
    try:
        method = event["requestContext"]["http"]["method"]
        params = event.get("pathParameters") or {}
        filename = params.get("filename")
        bucket = bucket_from_event(event)

        if method == "PUT" and filename:
            url = s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket, "Key": filename},
                ExpiresIn=900
            )
            return response(200, {"operation": "upload", "bucket": bucket, "key": filename, "url": url})

        if method == "GET" and filename:
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": filename},
                ExpiresIn=300
            )
            return response(200, {"operation": "download", "bucket": bucket, "key": filename, "url": url})

        if method == "DELETE" and filename:
            url = s3.generate_presigned_url(
                "delete_object",
                Params={"Bucket": bucket, "Key": filename},
                ExpiresIn=300
            )
            return response(200, {"operation": "delete", "bucket": bucket, "key": filename, "url": url})

        if method == "GET" and not filename:
            url = s3.generate_presigned_url(
                "list_objects_v2",
                Params={"Bucket": bucket},
                ExpiresIn=300
            )
            return response(200, {"operation": "list", "bucket": bucket, "url": url})

        return response(400, {"message": "Unsupported request"})

    except ValueError as e:
        return response(401, {"message": str(e)})
    except Exception:
        return response(500, {"message": "Internal server error"})