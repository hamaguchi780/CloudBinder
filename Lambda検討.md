# このLambdaは「何をするものか」

一言で言うと：

> **「mTLSで認証された端末に対して、その端末専用S3バケットへアクセスするための Presigned URL を発行する制御役」**

重要なのは：

* ❌ データを触らない
* ❌ S3操作を代行しない
* ✅ URLを“発行するだけ”
* ✅ 認証・認可の境界点になる

---

## ファイル全体の構造

```text
1. import / 初期化
2. 共通処理（CN取得・バケット決定）
3. メイン処理（lambda_handler）
   ├ PUT 用URL発行
   ├ GET 用URL発行
   ├ DELETE 用URL発行
   └ LIST（例外的にLambdaが実行）
```

---

## ① import / 初期化部分

```python
import boto3
import json
import os
from botocore.exceptions import ClientError
```

### 何をしている？

* `boto3`：AWSを操作する公式SDK
* `json`：APIの返却値をJSONにするため
* `os`：環境変数を読むため
* `ClientError`：AWSエラーを判別するため

---

```python
s3 = boto3.client("s3")
```

* Lambdaに割り当てられた **IAMロールの権限で**
* S3を操作できるクライアントを作成

👉 **アクセスキーは一切使っていない**
（IAMユーザー不使用方針どおり）

---

```python
PRESIGN_EXPIRE = int(os.environ.get("PRESIGN_EXPIRE", "3600"))
```

* Presigned URL の有効期限（秒）
* 環境変数がなければ **3600秒（1時間）**

👉

* コードを書き換えずに期限変更できる
* セキュリティレビューで説明しやすい

---

## ② 共通処理（認証・識別まわり）

### CN抽出

```python
def extract_cn(subject_dn: str) -> str:
```

### 何をしている？

クライアント証明書の情報は、こんな文字列で来る：

```text
CN=clinic-001,OU=Backup,O=Example
```

そこから

```text
clinic-001
```

だけを取り出す。

---

```python
for part in subject_dn.split(","):
```

* `,` で分割して
* `CN=...` の部分を探す

---

```python
if part.startswith("CN="):
    return part.replace("CN=", "")
```

* `CN=` を見つけたら
* `clinic-001` だけ返す

👉
**端末識別の唯一の情報源**になる。

---

## mTLS情報からCNを取る

```python
def get_client_cn(event) -> str:
```

Lambdaに渡される `event` の中に、
API Gateway が検証した **クライアント証明書情報**が入っている。

---

```python
event["requestContext"]["authentication"]["clientCert"]["subjectDN"]
```

### ここが超重要

* この情報は **API Gateway が mTLS で認証済み**
* Lambdaが勝手に信じているわけではない

👉
**「Lambdaが証明書検証していないのに大丈夫？」**
というレビュー質問に対する答えは：

> 検証は API Gateway が実施済み

---

## バケット名決定

```python
def resolve_bucket_name(cn: str) -> str:
    return f"binder-{cn}"
```

### 何をしている？

* CNから **サーバー側だけが知っている規則**で
* S3バケット名を決定

例：

```text
CN = clinic-001
↓
binder-clinic-001
```

👉
クライアントは **バケット名を知らなくていい**

---

## バケット存在確認（重要）

```python
def ensure_bucket_exists(bucket: str):
```

### なぜ必要？

あなたが選んだ設計判断：

> **S3バケットは勝手に作らせない**

これを**コードで強制する**部分。

---

```python
s3.head_bucket(Bucket=bucket)
```

* バケットが存在すればOK
* 存在しなければエラー

---

```python
if e.response["Error"]["Code"] == "404":
    raise ValueError("Bucket not found")
```

👉

* 初回接続時に自動作成しない
* 管理者が **事前に用意したバケットだけ**使える

＝ **事故防止・権限逸脱防止**

---

## ③ メイン処理（lambda_handler）

```python
def lambda_handler(event, context):
```

Lambdaが呼ばれたとき、**必ずここから始まる**

---

## HTTP情報取得

```python
method = event["requestContext"]["http"]["method"]
path = event["requestContext"]["http"]["path"]
```

* POST /presign/put
* POST /presign/get
  などを判定するため。

---

## クライアント識別フロー（最重要）

```python
cn = get_client_cn(event)
bucket = resolve_bucket_name(cn)
ensure_bucket_exists(bucket)
```

### ここでやっていること

1. mTLSで認証された証明書から CN取得
2. CN → バケット名決定
3. バケットが **事前に用意されているか確認**

👉
**この3行が「認証・認可の心臓部」**

---

## PUT / GET / DELETE

例：PUT

```python
url = s3.generate_presigned_url(
    ClientMethod="put_object",
    Params={"Bucket": bucket, "Key": key},
    ExpiresIn=PRESIGN_EXPIRE
)
```

### 何をしている？

* 「このURLを使ったら、このバケットのこのKeyにだけ書いていい」
* という **一時的な許可証**を作っている

👉

* URLが漏れても期限切れで無効
* IAM情報は含まれない

---

## LIST（例外）

```python
resp = s3.list_objects_v2(Bucket=bucket)
```

### なぜ Presigned URL じゃない？

S3は：

* ❌ List用 Presigned URL をサポートしていない

でも：

* LISTは **制御系の情報**
* データ転送ではない

👉
**Lambdaが直接実行して返すのが正解**

---

## エラーハンドリング

```python
except ValueError as e:
    return json_response(401, ...)
```

* 認証・認可・設計違反系
* バケットなし
* 証明書なし

👉 401（Unauthorized）

---

```python
except Exception:
    return json_response(500, ...)
```

* 想定外エラー
* 内部情報は返さない

---

## このコードのまとめ

| 設計方針         |  実装             |
| -----------      | --------------    |
| IAMユーザー不使用 | IAMロールのみ |
| mTLS認証      | API Gateway側   |
| CNで端末識別     | subjectDN → CN |
| データ系分離      | S3直通信          |
| バケット自動作成しない | head_bucket    |
| 監査しやすい      | 処理が単純          |

---
