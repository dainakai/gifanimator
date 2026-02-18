# GIF Animator アプリケーション仕様

## 概要
`GIF Animator` は、ローカル GIF を素早く確認するための Tkinter GUI アプリです。  
実装は `/Users/dai/Documents/repos/gifanimator/app.py` に集約されており、以下を提供します。

- GIF 読み込み（ファイル選択 / ドロップ）
- 再生・停止・速度切替（0.5x / 1x / 2x）
- フレーム移動（ボタン / スライダー / キーボード）
- 同一フォルダ GIF の一覧表示と巡回
- 現在フレームの書き出し（PNG/GIF）

## 依存関係
- Python `>=3.11`
- `pillow>=12.1.1`
- `tkinterdnd2>=0.4.3`
- Tkinter が利用可能な Python 実行環境

## 起動シーケンス
1. `tkinterdnd2` を読み込み（失敗時は起動中断）。
2. macOS の場合、`tkinterdnd2` の `tkdnd` ローダーをパッチしてアーキ別 dylib を明示ロード。
3. ルートウィンドウ作成後、HiDPI スケールを推定して `tk scaling` を設定。
4. Linux では利用可能フォントから UI/等幅フォントを選択して named font を再設定。
5. `GifAnimatorApp` を初期化して `mainloop()` 開始。

## UI 構成
- 左ペイン `Directory GIFs`
  - `GIFを開く`
  - 並び替えコンボ
  - `Treeview`（Name / Modified / Size）
  - `Prev File` / `Next File`
- 右ペイン `Preview`
  - 画像表示ラベル
  - `再生` / `停止`
  - `◀` / `▶`
  - 速度ラジオボタン（0.5x / 1x / 2x）
  - フレームスライダー
  - `現在フレームを保存`
- 下部
  - ステータスラベル（読み込み/保存結果・案内）

## 入力操作
- キーボード
  - `←` / `→`: フレーム移動
  - `↑` / `↓`: 同一フォルダ内ファイル移動
  - `Space`: 再生/停止トグル
- D&D
  - 受け取り: `DND_FILES` から最初に見つかった `.gif` を読み込み
  - 持ち出し: プレビューから現在ファイルのパスを提供
  - `file://` URI をパスに変換して処理

## GIF 読み込み仕様
- GIF 以外は `ValueError`。
- `ImageSequence.Iterator` ですべてのフレームを取得。
- 各フレーム遅延:
  - `frame.info["duration"]` を優先
  - なければ `img.info["duration"]` を利用
  - 最低 20ms に補正
- フレームが 0 の場合はエラー。

## 再生・描画仕様
- 再生タイマ最小遅延: `MIN_FRAME_DELAY_MS = 30`
- キャッシュ:
  - キー: `(frame_index, preview_width, preview_height)`
  - 上限: `FRAME_CACHE_LIMIT = 120`（LRU 的に古いものから削除）
- リサイズ:
  - 変化閾値: `RESIZE_EPSILON_PX = 2` を `ui_scale` で拡大
  - `80ms` デバウンス後に再描画
- プレビューサイズ未確定時の仮サイズ: `640x480`（`ui_scale` 適用）

## 一覧表示と並び替え
現在ファイルの親ディレクトリを走査し、`.gif` のみ表示。

並び替えキー:
- Name (A-Z)
- Name (Z-A)
- Time (Old-New)
- Time (New-Old)

## 保存仕様
- 保存対象: 現在表示中フレーム
- デフォルト名: `{元GIF名}_frame_0001.png` 形式
- 拡張子 `.gif` の場合のみ `P` モードへ変換して GIF 保存
- それ以外は Pillow 標準保存（通常 PNG）

## スケール・フォント関連
### HiDPI スケール推定の優先順
1. `GIF_ANIMATOR_UI_SCALE`（`0.5`〜`4.0`）
2. `GDK_SCALE * GDK_DPI_SCALE`
3. `QT_SCALE_FACTOR`
4. `xrdb -query` の `Xft.dpi`
5. `root.winfo_fpixels("1i")`

推定後に `0.75`〜`3.0` へ clamp し、`tk scaling = (96/72) * ui_scale` を適用。

### フォント選択
- Linux のみ自動選択を実施
- `GIF_ANIMATOR_FONT_FAMILY` / `GIF_ANIMATOR_FIXED_FONT_FAMILY` で上書き可能
- `TkDefaultFont` など named font を `ui_scale` 倍して再設定

## macOS / Ubuntu 環境構築メモ
### macOS
- Homebrew か python.org の Python 3.11+ を使用する。
- 依存導入:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -U pip
  python -m pip install "pillow>=12.1.1" "tkinterdnd2>=0.4.3"
  ```
- `python -m tkinter` で Tk が起動することを確認。

### Ubuntu
- `python3-tk` が必須。
- 推奨セットアップ:
  ```bash
  sudo apt update
  sudo apt install -y \
    python3 python3-venv python3-pip python3-tk \
    x11-xserver-utils fonts-noto-cjk
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -U pip
  python -m pip install "pillow>=12.1.1" "tkinterdnd2>=0.4.3"
  ```

## 既知の制約
- 巨大 GIF は全フレームを Pillow で保持するためメモリ消費が大きい。
- `main()` 内の `if app.current_file:` は初期値が `None` のため通常は実行されない。
- D&D 可否は OS/Tk/TkDND の組み合わせに依存する。
