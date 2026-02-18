# GIF Animator

ローカル GIF を軽快に確認するための Tkinter デスクトップアプリです。  
`app.py` 単体で動作し、再生・フレーム移動・同一フォルダ内 GIF の連続閲覧・フレーム保存に対応しています。

## 主な機能
- GIF の読み込み（ファイル選択 / ドラッグ&ドロップ）
- 再生 / 停止、0.5x / 1x / 2x 速度切り替え
- フレーム単位の移動（ボタン・スライダー・左右キー）
- 同一ディレクトリ内 GIF 一覧表示と並び替え
- `Prev File` / `Next File` と上下キーでファイル移動
- 表示中フレームの保存（PNG または GIF）

## 必要要件
- Python `3.11` 以上
- Tkinter が使える Python
- Python パッケージ
  - `pillow>=12.1.1`
  - `tkinterdnd2>=0.4.3`

## セットアップ

### macOS 向け
Homebrew Python または python.org の Python 3.11+ を推奨します（`/usr/bin/python3` は古い場合あり）。

```bash
# 1) Python 3.11+ を用意（未導入なら）
brew install python@3.12

# 2) 仮想環境
python3 -m venv .venv
source .venv/bin/activate

# 3) 依存パッケージ
python -m pip install -U pip
python -m pip install "pillow>=12.1.1" "tkinterdnd2>=0.4.3"
```

動作確認:
```bash
python -m tkinter
```
小さな Tk ウィンドウが出れば OK です。

### Ubuntu 向け
`python3-tk` がないと GUI が起動しません。HiDPI 検出補助のため `x11-xserver-utils`（`xrdb`）も推奨です。

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

## 起動
```bash
source .venv/bin/activate
python app.py
```

## 操作
- `GIFを開く`: GIF ファイルを選択して読み込み
- `再生` / `停止`: アニメーション制御
- `◀` / `▶`: 1 フレームずつ移動
- `Prev File` / `Next File`: 同一フォルダの GIF を巡回
- `現在フレームを保存`: 表示中フレームを保存

ショートカット:
- `←` / `→`: 前後フレーム
- `↑` / `↓`: 前後ファイル
- `Space`: 再生 / 停止トグル

## Linux で表示が小さい/フォントが崩れる場合
環境変数で調整できます。

```bash
export GIF_ANIMATOR_UI_SCALE=1.5
export GIF_ANIMATOR_FONT_FAMILY="Noto Sans CJK JP"
export GIF_ANIMATOR_FIXED_FONT_FAMILY="Noto Sans Mono CJK JP"
python app.py
```

`GDK_SCALE`, `GDK_DPI_SCALE`, `QT_SCALE_FACTOR` も参照されます。

## トラブルシュート
- `No module named '_tkinter'`:
  - Ubuntu: `sudo apt install python3-tk`
  - macOS: Homebrew か python.org の Python を使用
- `tkinterdnd2 の読み込みに失敗`:
  - 仮想環境を有効化して再インストール  
    `python -m pip install --force-reinstall tkinterdnd2`
- 起動できるが D&D が効かない:
  - Python と Tcl/Tk のアーキテクチャ不一致の可能性あり（特に macOS）。同じ配布元の Python に統一してください。

## 詳細仕様
実装準拠の仕様は `/Users/dai/Documents/repos/gifanimator/docs/gif_animator_app.md` を参照してください。
