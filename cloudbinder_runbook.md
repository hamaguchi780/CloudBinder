# CloudBinder 運用手順書

本書は、CloudBinder プロジェクトにおける **設計確定後〜本番運用まで** の
AWS 側およびクライアント側の運用手順を体系的にまとめた Runbook である。

---

## 1. 前提・基本方針

### 1.1 システム概要

- オンプレミス（Windows 端末）から Amazon S3 へバックアップデータを保存
- Presigned URL を用いた **S3 直接アップロード方式**
- API Gateway + Lambda は **Presigned URL 発行専用**
- データ転送は **クライアント ⇔ S3** のみ

### 1.2 セキュリティ方針

- API Gateway：TLS + mTLS
- クライアント識別：証明書 CN
- IAM ユーザー不使用
- S3 直接アクセスは Presigned URL のみ許可
- バックアップ用 S3 は **SSE-S3**

### 1.3 CloudFormation 管理方針

- すべての AWS リソースは原則 CloudFormation で管理
- スタックは「アカウント共通」と「アプリケーション用」に分離

---

## 2. スタック構成と責務

### 2.1 アカウント共通スタック

| Stack | 内容 | 備考 |
|---|---|---|
| 00-security-global | GuardDuty / Malware Protection for S3 | 1アカウント1回 |
| 02-logging | CloudTrail / 監査ログ用 S3 / KMS | Env 非依存 |

### 2.2 アプリケーションスタック（Env ごと）

| Stack | 内容 |
|---|---|
| cf_binder_s3 | バックアップ用 S3 バケット |
| cf_binder_lambda_api | API Gateway / Lambda / IAM |

---

## 3. 初期構築手順

### 3.1 アカウント共通基盤の構築

#### 3.1.1 GuardDuty / Malware Protection

```sh
aws cloudformation deploy \
  --template-file 00-security-global.yaml \
  --stack-name security-global
```

**確認事項**

- GuardDuty Detector が ENABLED
- Malware Protection が S3 全体を対象

---

#### 3.1.2 CloudTrail / 監査ログ

```sh
aws cloudformation deploy \
  --template-file 02-logging.yaml \
  --stack-name logging
```

**確認事項**

- CloudTrail が Multi-Region
- S3 にログが出力され始めている

---

### 3.2 アプリケーション基盤の構築（Env 単位）

#### 3.2.1 S3（バックアップ用）

```sh
aws cloudformation deploy \
  --template-file cf_binder_s3.yaml \
  --stack-name binder-s3-stg \
  --parameter-overrides Env=stg
```

**確認事項**

- SSE-S3 有効
- Presigned URL 以外のアクセスが拒否される

---

#### 3.2.2 Lambda + API Gateway

```sh
aws cloudformation deploy \
  --template-file cf_binder_lambda_api.yaml \
  --stack-name binder-api-stg \
  --parameter-overrides Env=stg
```

**確認事項**

- mTLS が有効
- Lambda が S3 操作を直接行っていない

---

## 4. クライアント運用

### 4.1 クライアント証明書管理

- CA でクライアント証明書を発行
- CN は端末ごとに一意
- CN 変更＝新端末扱い

**失効時対応**

- 証明書失効
- API Gateway への接続不可となる

---

### 4.2 クライアントアプリ動作概要

1. API Gateway へ mTLS 接続
2. Presigned URL を取得
3. URL を使って S3 へ直接 PUT / GET / DELETE

※ クライアントは **バケット名を知らない**

---

## 5. 運用・保守

### 5.1 証明書更新

- 有効期限前に再発行
- CN を変更しない限り S3 側影響なし

---

### 5.2 障害対応

| 事象 | 確認ポイント |
|---|---|
| API が 401 | 証明書 CN / 失効確認 |
| S3 403 | URL 期限切れ |
| Upload 失敗 | バケット存在 / 権限 |

---

### 5.3 監査・セキュリティ対応

- CloudTrail：全 API 操作記録
- GuardDuty：異常検知
- Malware Protection：S3 オブジェクトスキャン

---

## 6. 変更管理

### 6.1 変更手順

1. CloudFormation テンプレート修正
2. stg 環境へデプロイ
3. 動作確認
4. prod へ反映

---

## 7. 注意事項

- GuardDuty / CloudTrail は **プロジェクト分離不可**
- バックアップ用 S3 とログ用 S3 は完全に別運用
- IAM ユーザーは一切使用しない

---

## 8. 付録

### 用語

- Presigned URL：署名付き S3 アクセス URL
- mTLS：相互 TLS 認証
- CN：証明書の Common Name

---
