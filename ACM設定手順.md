## 第2章 ルートCA作成 手順（信頼の起点）

本章では、本システムにおける信頼の起点となるルートCAを作成するための具体的な操作手順を示す。ルートCAは証明書発行の直接対象としては使用せず、中間CAを発行・署名する目的に限定して利用する。

---

### ■ 作業対象

- AWS Private Certificate Authority（ACM Private CA）

### ■ 作業者

- AWS管理者（セキュリティ管理権限を有する者）

### ■ 前提条件

- AWSアカウントに管理者権限でログイン可能であること
- 利用リージョンが確定していること（例：ap-northeast-1）
- ルートCAは信頼の起点として管理し、通常運用では使用しない方針であること

---

## 2.1 コンソール操作手順

### 2.1.1 ACM Private CA 画面の表示

1. AWSマネジメントコンソールにログイン
2. サービス一覧から **ACM Private CA** を選択
3. 「プライベート認証局を作成」をクリック

### 2.1.2 認証局タイプの選択

- 認証局タイプ：**ルートCA** を選択
- 「次へ」をクリック

### 2.1.3 CA 構成（キーと署名アルゴリズム）

以下を設定する。

- キーアルゴリズム：RSA 4096
- 署名アルゴリズム：SHA-384 with RSA

※ 医療情報ガイドラインおよび高セキュリティ型要件を満たす構成とする。

### 2.1.4 Subject 情報（CA 識別情報）

以下は例であり、実際の組織情報に合わせて設定する。

- 共通名（CN）：Example-Root-CA
- 組織（O）：Example Organization
- 組織単位（OU）：Security
- 国（C）：JP

※ ここで設定するCNは「CA識別用」であり、クライアント識別用CNとは用途が異なる。

### 2.1.5 有効期間の設定

- 有効期間：10年以上（例：20年）

※ ルートCAは長期的な信頼の起点として位置付ける。

### 2.1.6 作成確認

- 設定内容を確認し、「認証局を作成」を実行

---

## 2.2 CLI 操作手順（代替手段）

### 2.2.1 設定ファイル作成（例）

```json
{
  "KeyAlgorithm": "RSA_4096",
  "SigningAlgorithm": "SHA384WITHRSA",
  "Subject": {
    "Country": "JP",
    "Organization": "Example Organization",
    "OrganizationalUnit": "Security",
    "CommonName": "Example-Root-CA"
  }
}
```

### 2.2.2 認証局作成コマンド

```bash
aws acm-pca create-certificate-authority \
  --certificate-authority-type ROOT \
  --certificate-authority-configuration file://root-ca-config.json \
  --region ap-northeast-1
```

※ 出力される ARN を控える。

---

## 2.3 認証局証明書の発行

### 2.3.1 コンソール

1. 作成したルートCAを選択
2. 「認証局証明書をインストール」を実行
3. 証明書タイプ：**自己署名**
4. 署名アルゴリズム：SHA-384
5. 有効期間：CA有効期間と同等

### 2.3.2 CLI（参考）

```bash
aws acm-pca issue-certificate \
  --certificate-authority-arn <RootCA-ARN> \
  --csr file://root.csr \
  --signing-algorithm SHA384WITHRSA \
  --validity Value=7300,Type=DAYS
```

---

## ■ 作業結果（次工程への引き渡し）

- ルートCAが作成され、認証局証明書がインストールされていること
- ルートCA ARN が取得できていること

本結果をもって、次章「第3章 中間CA作成」に進む。
