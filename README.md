# Channel Works YouTube DL Bot

Channel Works の指定グループに投稿された YouTube URL から動画を取得し、添付返信する bot。

## 動作

1. 指定グループをポーリング
2. 直近 N 件の未処理メッセージから YouTube URL を検出（同一 videoId は 1 件）
3. **yt-dlp** で取得（ffmpeg あり: 最高画質結合 / なし: progressive）
4. 取得ファイルをメッセージに添付して返信（失敗時は固定文言で通知）
5. 取得はワーカースレッドで実行し、検知ループは止めない

ダウンロードは常に以下の制約下で行う：

- 許可ホスト（youtube.com / youtu.be 系）以外の URL は拒否（`stream.py` と
  yt-dlp の `allowed_extractors` による二重チェック）
- 単一動画の videoId を抽出できない URL（プレイリスト・チャンネルページ等）は
  検出の時点で除外し、`stream.py` と yt-dlp オプション（`playlist_items`）・
  応答種別チェックでも重ねて拒否する（三重チェック。無制限ダウンロード防止）
- bot 自身が送信したメッセージ（成功/失敗の返信）は送信直後に処理済み登録し、
  次回以降のポーリングで新規メッセージとして誤検出しない（自己ループ防止）
- ライブ配信中の動画は実ダウンロード開始前に拒否（無制限ダウンロード防止）
- ファイルサイズ上限（既定 2000MB、`YT_MAX_FILESIZE_MB` で変更可）

## モジュール構成

| モジュール | 役割 |
|------------|------|
| `main.py` | プロセスエントリポイント（ログ設定・起動） |
| `bot.py` | ポーリング・ジョブ投入・実行時ライフサイクル管理 |
| `tmp_cleanup.py` | 起動時の孤児一時ディレクトリ掃除 |
| `job_runner.py` | ダウンロードジョブの実行・成功/失敗の返信 |
| `channel_client.py` | Desk API のメッセージ送受信（高レベル API） |
| `channel_session.py` | 認証付き HTTP 実行層（credential 同期・401 リカバリ・ネットワークリトライ） |
| `token_refresher.py` | account/touch による token refresh の試行ロジック |
| `channel_http.py` | HTTP 定数・ヘッダ・requestId・エラー型判定 |
| `channel_media.py` | 公開メッセージ用メディアアップロード |
| `account_auth.py` | x-account (JWT) の保持・送信要否判定 |
| `session_credentials.py` | ch-session-1 / ch-veil-id / x-account-refresh Cookie の保持 |
| `jwt_token.py` | JWT payload のデコード・有効期限抽出 |
| `server_clock.py` | サーバー応答 Date ヘッダーによる時刻ズレ補正 |
| `http_headers.py` | HTTP ヘッダー取得の共通ヘルパー |
| `cookie_jar_utils.py` | RequestsCookieJar の同名 Cookie 衝突を避ける安全アクセス |
| `stream.py` | ダウンロード公開入口（URL・単一動画検証を含む） |
| `stream_ytdlp.py` | yt-dlp 実行（ダウンロード〜結果ファイルの解決） |
| `ytdlp_options.py` | yt-dlp オプション組み立て（リソース上限・抽出器制限） |
| `youtube_url.py` | URL 検出・videoId 抽出（単一動画のみ） |
| `message_tracker.py` | 処理済みメッセージ追跡 |
| `reply_formatter.py` | 返信文言整形 |
| `models.py` | 共有ドメインモデル（`StreamInfo`） |
| `exceptions.py` | 共有例外クラス |
| `config.py` | 環境変数 |

## 認証（フロント準拠）

| 項目 | 内容 |
|------|------|
| 初期 token | `CH_X_ACCOUNT` |
| 送信 | `x-account`（未所持・期限切れは付けない） |
| 更新 | 応答ヘッダ `x-account` |
| 時刻補正 | `Date` + `cache-control` |
| refresh | リクエスト前 `shouldRefreshToken` → `POST /desk/account/touch` |
| touch パラメータ | `refreshOnly=true`, `skipSessionExtension=true` |
| 401 リカバリ | 終端 type 以外のみ force refresh 後 1 回リプレイ |
| requestId | `desk-web-{epochMs}{base36×4}` |

## 環境変数

ブラウザで [channel.works](https://channel.works) にログインし、DevTools から取得する。

### 必須

| 変数 | 取得元 |
|------|--------|
| `CH_X_ACCOUNT` | Cookie `x-account` |
| `CH_SESSION_COOKIE` | Cookie `ch-session-1` |
| `CH_VEIL_ID` | Cookie `ch-veil-id` |
| `CH_X_ACCOUNT_REFRESH` | Cookie `x-account-refresh`（`x-account`とは別値） |
| `CH_CHANNEL_ID` | URL `/desk/channels/<ID>/...` |
| `CH_GROUP_YOUTUBE_DL` | URL `/groups/<ID>/messages` |

### 任意

| 変数 | 既定 | 説明 |
|------|------|------|
| `MESSAGE_FETCH_LIMIT` | `20` | 1 回の取得件数 |
| `YT_WORKERS` | `2` | yt-dlp ワーカー数（最大 16） |
| `HTTP_TIMEOUT` | `15` | API タイムアウト（秒） |
| `POLL_IDLE_SLEEP` | `0.5` | 新規なし時の待ち（秒） |
| `YT_MAX_FILESIZE_MB` | `2000` | 1 動画あたりの最大ダウンロードサイズ（MB） |

## セットアップ

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 最高画質結合には ffmpeg が必要
cp .env.example .env
# .env を編集
python main.py
```
