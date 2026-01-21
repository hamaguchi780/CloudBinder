# CloudBinder

クラウドバインダー実装用
事前に用意するもの（初回のみ）

## ドメインとACM証明書

- DomainName：例 binder-prod.example.com / binder-stg.example.com
- CertificateArn：各ドメインに対応するACM ARN（同一でも可）

## mTLS TrustStore（S3）

- TrustStoreBucket：PEMを置くバケット
- TrustStoreKey：例 truststore/ca.pem
  - ※API Gatewayが読むので、このオブジェクトを参照できる状態にしておく

## coreスタック用の入力値を確定

- Env：prod / stg
- ApiNamePrefix：通常 binder
- StageName：推奨 $default（テンプレ既定）
- レート制限：ApiRateLimit / ApiBurstLimit
- Lambda設定：必要なら LambdaReservedConcurrency 等

## core統合テンプレ作成時（prod/stg各1回）

### CloudFormation作成画面で以下を入力

- Env：prod（またはstg）
- DomainName：binder-prod.example.com（またはstg）
- CertificateArn：対応するACM ARN
- TrustStoreBucket / TrustStoreKey
- （任意）スロットリング、Lambda名/メモリ等

### 作成後に確認

- Outputsの ApiDomainEndpoint にアクセスできること
- クライアント証明書付きで疎通できること（CNが取れること）

## 端末S3テンプレ作成時（端末追加ごと）

### 入力（必須）

- Env：prod or stg
- ClientCN：証明書のCN（例 ABC001）

## 作成されるもの

- バケット名：binder-{env}-{CN}（例 binder-prod-ABC001）
