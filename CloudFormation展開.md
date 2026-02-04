# CloudFormation 設計・展開手順書

本書は、CloudBinder プロジェクトにおける **AWS 環境の設計方針および CloudFormation による展開手順**を示すものである。

---

## 1. 前提・基本方針

### 1.1 システム概要

* オンプレミス（Windows 端末）から Amazon S3 へバックアップデータを保存する
* データ転送は **Presigned URL を用いた S3 直接アクセス方式**を採用する
* API Gateway および Lambda は **Presigned URL 発行専用の Control Plane**として機能する
* バックアップデータの実体転送は **クライアント ⇔ S3 間のみ**で行われる

---

### 1.2 セキュリティ方針

* API Gateway は TLS + mTLS（相互 TLS 認証）を必須とする
* クライアント識別は証明書の **Common Name（CN）** により行う
* IAM ユーザーは使用しない
* S3 への直接アクセスは Presigned URL のみ許可する
* バックアップデータ用 S3 バケットは **SSE-S3 による暗号化**を使用する

---

### 1.3 CloudFormation 管理方針

* すべての AWS リソースは原則 CloudFormation で管理する
* スタックは以下の観点で分離する

  * **アカウント共通・削除厳禁な基盤**
  * **アプリケーション（Control Plane）**
* 誤操作による全体消失を防ぐため、役割ごとに独立したスタック構成とする

---

## 2. スタック構成と責務

### 2.1 使用する CloudFormation テンプレート一覧

| Stack                        | 役割                                     |
| ---------------------------- | -------------------------------------- |
| stack_security_baseline.yaml | アカウント共通の監査・検知・ログ基盤                     |
| private-ca.yaml              | mTLS 用 Private CA（信頼の根）                |
| iam-cert-operations.yaml     | 証明書発行・失効を行う運用 IAM 権限                   |
| stack_control_plane.yaml     | API Gateway + Lambda（Presigned URL 発行） |

---

### 2.2 各スタックの責務

#### stack_security_baseline.yaml

* CloudTrail（Multi-Region）
* AWS Config
* GuardDuty
* GuardDuty Malware Protection for S3
* 監査ログ保存用 S3 バケット

※ アカウント共通。削除・再作成は原則禁止。

---

#### private-ca.yaml

* ACM Private CA の作成
* mTLS クライアント証明書の信頼の根を提供

※ 削除すると全クライアントが即時無効となるため、特に慎重に扱う。

---

#### iam-cert-operations.yaml

* Private CA を操作するための IAM Role / Policy
* クライアント証明書の発行・失効・更新を運用として分離

---

#### stack_control_plane.yaml

* API Gateway（HTTP API）
* mTLS 設定（Private CA を参照）
* Presigned URL 発行用 Lambda
* バックアップ操作の制御プレーン

---

## 3. CloudFormation 展開手順（CLI）

### 3.1 展開順序（重要）

1. stack_security_baseline.yaml
2. private-ca.yaml
3. iam-cert-operations.yaml
4. stack_control_plane.yaml

---

### 3.2 stack_security_baseline.yaml

```sh
aws cloudformation deploy \
  --stack-name stack-security-baseline \
  --template-file stack_security_baseline.yaml \
  --capabilities CAPABILITY_NAMED_IAM
```

---

### 3.3 private-ca.yaml

```sh
aws cloudformation deploy \
  --stack-name stack-private-ca \
  --template-file private-ca.yaml \
  --capabilities CAPABILITY_NAMED_IAM
```

---

### 3.4 iam-cert-operations.yaml

```sh
aws cloudformation deploy \
  --stack-name stack-iam-cert-operations \
  --template-file iam-cert-operations.yaml \
  --capabilities CAPABILITY_NAMED_IAM
```

---

### 3.5 stack_control_plane.yaml

#### 事前準備（Lambda コード）

* Lambda の実装コードを ZIP 化し、S3 に配置する
* CloudFormation からは S3 上のコードを参照する

```sh
zip lambda-presign.zip app.py
aws s3 cp lambda-presign.zip s3://<lambda-code-bucket>/lambda-presign.zip
```

#### デプロイ

```sh
aws cloudformation deploy \
  --stack-name stack-control-plane \
  --template-file stack_control_plane.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    LambdaCodeBucket=<bucket-name> \
    LambdaCodeKey=lambda-presign.zip
```

---

## 4. クライアント運用

### 4.1 クライアント証明書管理

* Private CA によりクライアント証明書を発行
* CN は端末ごとに一意
* CN を変更した場合は新端末扱いとなる

---

### 4.2 クライアントアプリ動作概要

1. クライアントが mTLS で API Gateway に接続
2. Presigned URL を取得
3. URL を使用して S3 へ直接 PUT / GET / DELETE / LIST を実行

※ クライアントは S3 バケット名を直接認識しない。

---

## 5. 運用・保守

### 5.1 障害対応

| 事象        | 確認ポイント              |
| --------- | ------------------- |
| API が 401 | 証明書 CN / 失効状態       |
| S3 が 403  | Presigned URL の期限切れ |
| Upload 失敗 | バケット存在 / 権限         |

---

## 6. 注意事項

* セキュリティ基盤（CloudTrail / GuardDuty 等）はプロジェクト分離不可
* バックアップ用 S3 とログ用 S3 は完全に別運用とする
* IAM ユーザーは一切使用しない

---
