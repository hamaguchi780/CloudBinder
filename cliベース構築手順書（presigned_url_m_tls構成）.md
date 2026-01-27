# AWS CLIベース 環境構築手順書

本手順書は、AWSマネジメントコンソールは**確認用途のみ**とし、
**AWS CLIを用いて構築・設定すること**を前提とする。

---

## 0. 前提条件

- AWS CLI v2 インストール済み
- 実行ロール／ユーザーは AdministratorAccess 相当（初期構築時のみ）
- リージョン：ap-northeast-1（東京）※仮

```bash
aws configure
```

---

## 1. KMS キー作成（バックアップ系共通キー）

※ 本キーは **S3 / Lambda / 将来EC2 で共通利用**する前提
※ 自動ローテーションは必須要件としない
※ 削除猶予期間は最大（30日）を設定すること

### 1.1 KMSキー作成

```bash
aws kms create-key \
  --description "S3 Backup Encryption Key" \
  --key-usage ENCRYPT_DECRYPT \
  --origin AWS_KMS
```

出力された `KeyId` を控える。

### 1.2 エイリアス作成

```bash
aws kms create-alias \
  --alias-name alias/s3-backup-key \
  --target-key-id <KeyId>
```

---

## 2. S3 バケット作成（端末単位で動的利用）

※ Lambda が動的に参照するため、ここでは**サンプル用**として1バケット作成

```bash
aws s3api create-bucket \
  --bucket backup-bucket-sample-001 \
  --region ap-northeast-1 \
  --create-bucket-configuration LocationConstraint=ap-northeast-1
```

### 2.1 バージョニング有効化

```bash
aws s3api put-bucket-versioning \
  --bucket backup-bucket-sample-001 \
  --versioning-configuration Status=Enabled
```

### 2.2 SSE-KMS 設定

```bash
aws s3api put-bucket-encryption \
  --bucket backup-bucket-sample-001 \
  --server-side-encryption-configuration '{
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "aws:kms",
          "KMSMasterKeyID": "alias/s3-backup-key"
        }
      }
    ]
  }'
```

---

## 3. ACM Private CA 構築（mTLS用）

### 3.1 Private CA 作成

```bash
aws acm-pca create-certificate-authority \
  --certificate-authority-type ROOT \
  --certificate-authority-configuration '{
    "KeyAlgorithm": "RSA_2048",
    "SigningAlgorithm": "SHA256WITHRSA",
    "Subject": {
      "Country": "JP",
      "Organization": "SampleOrg",
      "OrganizationalUnit": "IT",
      "CommonName": "BackupClientRootCA"
    }
  }'
```

CA ARN を控える。

### 3.2 自己署名証明書発行

```bash
aws acm-pca get-certificate-authority-csr \
  --certificate-authority-arn <CA_ARN> > ca.csr
```

```bash
aws acm-pca issue-certificate \
  --certificate-authority-arn <CA_ARN> \
  --csr file://ca.csr \
  --signing-algorithm SHA256WITHRSA \
  --validity Value=3650,Type=DAYS
```

---

## 4. Lambda 用 IAM ロール作成

### 4.1 信頼ポリシー作成

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

```bash
aws iam create-role \
  --role-name lambda-presign-role \
  --assume-role-policy-document file://trust-policy.json
```

### 4.2 ポリシーアタッチ

```bash
aws iam attach-role-policy \
  --role-name lambda-presign-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
```

```bash
aws iam attach-role-policy \
  --role-name lambda-presign-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

---

## 5. Lambda 関数作成（Presigned URL 発行）

### 5.1 Lambda 作成

```bash
aws lambda create-function \
  --function-name presign-url-function \
  --runtime python3.11 \
  --role arn:aws:iam::<ACCOUNT_ID>:role/lambda-presign-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function.zip
```

※ function.zip には CN 取得・Presigned URL 生成ロジックを実装

---

## 6. API Gateway（HTTP API）作成

### 6.1 HTTP API 作成

```bash
aws apigatewayv2 create-api \
  --name presign-http-api \
  --protocol-type HTTP
```

出力される `ApiId` を控える。

---

### 6.2 Lambda Integration 作成

```bash
aws apigatewayv2 create-integration \
  --api-id <API_ID> \
  --integration-type AWS_PROXY \
  --integration-uri arn:aws:lambda:ap-northeast-1:<ACCOUNT_ID>:function:presign-url-function \
  --payload-format-version 2.0
```

出力される `IntegrationId` を控える。

---

### 6.3 Route（ルーティング）作成

本APIでは制御ロジックをすべてLambdaに集約するため、
すべて同一Integrationを使用する。

```bash
aws apigatewayv2 create-route \
  --api-id <API_ID> \
  --route-key "POST /presign/put" \
  --target integrations/<INTEGRATION_ID>
```

```bash
aws apigatewayv2 create-route \
  --api-id <API_ID> \
  --route-key "POST /presign/get" \
  --target integrations/<INTEGRATION_ID>
```

```bash
aws apigatewayv2 create-route \
  --api-id <API_ID> \
  --route-key "POST /presign/delete" \
  --target integrations/<INTEGRATION_ID>
```

```bash
aws apigatewayv2 create-route \
  --api-id <API_ID> \
  --route-key "POST /presign/list" \
  --target integrations/<INTEGRATION_ID>
```

---

### 6.4 Lambda 実行許可付与

```bash
aws lambda add-permission \
  --function-name presign-url-function \
  --statement-id apigateway-invoke \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn arn:aws:execute-api:ap-northeast-1:<ACCOUNT_ID>:<API_ID>/*
```

---

### 6.5 Stage 作成（$default）

```bash
aws apigatewayv2 create-stage \
  --api-id <API_ID> \
  --stage-name $default \
  --auto-deploy
```

---

※ 本段階では mTLS は未設定。通信制御は後続手順で実施する。

---

## 7. API Gateway mTLS 設定

### 7.1 信頼ストア用 S3 バケット作成

```bash
aws s3api create-bucket \
  --bucket mtls-truststore-bucket \
  --region ap-northeast-1
```

### 7.2 CA証明書アップロード

```bash
aws s3 cp ca.pem s3://mtls-truststore-bucket/ca.pem
```

### 7.3 カスタムドメイン & mTLS 有効化

```bash
aws apigateway create-domain-name \
  --domain-name api.example.local \
  --regional-certificate-arn <ACM_CERT_ARN> \
  --endpoint-configuration types=REGIONAL \
  --mutual-tls-authentication truststoreUri=s3://mtls-truststore-bucket/ca.pem
```

---

## 8. Route53 設定

```bash
aws route53 change-resource-record-sets \
  --hosted-zone-id <ZONE_ID> \
  --change-batch file://route53.json
```

---

## 9. 監査・検知系

※ 設計方針追加：CloudTrail は **全リージョン・組織全体** を前提とする

### 9.1 CloudTrail 有効化

```bash
aws cloudtrail create-trail \
  --name backup-trail \
  --s3-bucket-name cloudtrail-log-bucket \
  --is-multi-region-trail

aws cloudtrail start-logging --name backup-trail
```

### 9.2 GuardDuty 有効化

```bash
aws guardduty create-detector --enable
```

---

## 10. 確認事項（コンソール）

- API Gateway mTLS 接続確認
- Lambda ログ出力
- S3 直接アップロード可否
- CloudTrail / GuardDuty 動作

---

---

## 11. 将来拡張に関する前提条件（明文化）

- IAMユーザーは引き続き使用しない
- 人によるAWS操作は将来的に **IAM Identity Center** を想定
- EC2 / VPC / Systems Manager（SSM）は現時点では構築しない
- ただし以下の前提を否定しない

  - EC2追加時は IAMロール + SSM 管理
  - Private Subnet / VPC Endpoint 構成への移行余地を残す

---

以上
