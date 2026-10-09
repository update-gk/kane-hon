# お金の本トラッカー（発売日と売れ筋）

投資・お金の教養・副業の本だけを対象に、**発売予定カレンダー**と**売れ筋ランキング**を実際の表紙画像つきで表示するWebアプリです。
楽天ブックスAPIから毎日自動でデータを更新します（GitHub Actions）。購入先リンクはAmazonです。

## ファイル

| ファイル | 役割 |
| --- | --- |
| `index.html` | 画面（1ファイル）。`books.json` を読み込んで表示。なければサンプル表示 |
| `fetch_books.py` | 楽天ブックスAPIから本を集めて `books.json` を作る |
| `.github/workflows/update-books.yml` | 毎日 日本時間6時に `fetch_books.py` を実行して保存 |

## セットアップ（ブラウザだけで完結）

### 1. GitHubにリポジトリを作る
1. GitHubで **New repository**（名前の例: `kane-hon`、**Public**）を作成。
2. このzipを展開し、中身をすべてリポジトリにアップロード（**Add file → Upload files**）。
   `.github` フォルダも一緒にアップロードしてください。

### 2. 楽天ウェブサービスでアプリを登録する
1. https://webservice.rakuten.co.jp/app/create で新規アプリを登録。
2. **許可されたWebサイト**には、公開先のドメイン `ユーザー名.github.io` を入力（例: ユーザー名が `takamichi` なら `takamichi.github.io`）。
3. 登録後、**アプリID（applicationId）** と **アクセスキー（accessKey）** をコピー。

### 3. GitHubに2つの値を登録する
リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で次の2つを作成。

| Name | Secret |
| --- | --- |
| `RAKUTEN_APP_ID` | 楽天のアプリID |
| `RAKUTEN_ACCESS_KEY` | 楽天のアクセスキー |

### 4. ページを公開する
**Settings → Pages → Build and deployment** で、Source を **Deploy from a branch**、Branch を **main / (root)** にして Save。
公開URLは `https://ユーザー名.github.io/リポジトリ名/` です。

### 5. 最初のデータを取得する
**Actions** タブ → **update-books** → **Run workflow**。
1〜2分で `books.json` が作られ、ページが実データ（表紙画像つき）に切り替わります。以降は毎日自動更新されます。

## うまくいかないとき

- **Actionsのログに 403 / REFERRER と出る**: 楽天アプリの「許可されたWebサイト」が `ユーザー名.github.io` と一致しているか確認。
- **400 と出る**: アプリIDとアクセスキーの両方が、Secretsに正しく入っているか確認。
- **429 と出る**: アクセス過多です。少し時間をおいて再実行してください（スクリプトは自動で数回再試行します）。
- **ページがサンプルのまま**: `books.json` がまだ作られていません。手順5を実行してください。
- **本が少ない／多すぎる**: `fetch_books.py` の `CATEGORY_RULES`（書名に含まれるキーワード）を編集すると、対象の本を調整できます。

## メモ

- 対象は、楽天ブックスの「ビジネス」系ジャンルのうち、書名・副題にお金関連のことばを含む本です。
- ランキングは楽天ブックスの売れ順から、対象の本だけを上位20冊まで。矢印は前回（前日）の取得結果との比較です。
- 表紙画像は楽天ブックスのAPIが返す画像URLをそのまま使っています。画像が読み込めない本は、縦書きの簡易表紙になります。
- 楽天ウェブサービスの利用規約（クレジット表記など）は、公開前に一度確認してください。
