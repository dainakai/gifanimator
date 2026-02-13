# GIF Animator アプリケーション仕様

## 概要
`GIF Animator` は、ローカルの GIF アニメーションを軽量に閲覧するためのデスクトップ GUI アプリケーションです。  
Python 標準の `tkinter` と画像処理ライブラリ `Pillow` を使って実装しており、ブラウザやサーバーを起動せずに利用できます。

## 対応要件
1. GIF の読み込みと再生制御
- 任意の GIF ファイルを開く
- 再生 / 停止
- 0.5x / 1x / 2x 再生速度切り替え
- プレビュー領域のサイズに合わせて自動リサイズ表示

2. フレーム移動
- スライダーで任意フレームへ移動
- `◀` / `▶` ボタンで前後フレームへ移動
- キーボード左右キー（`←` `→`）でも移動

3. 同一ディレクトリの GIF 検出と一覧表示
- 開いた GIF と同じディレクトリ内の `.gif` を自動検出
- ファイル一覧を表示
- 以下の並び替えに対応
  - Name (A-Z)
  - Name (Z-A)
  - Time (Old-New)
  - Time (New-Old)
- `Prev File` / `Next File` で連続閲覧

4. 途中フレームの保存
- 表示中フレームを任意名で保存
- 既定は PNG 保存（GIF 保存も選択可能）

## パフォーマンス方針
- GIF 読み込み時に全フレームの `PhotoImage` 生成を行わない
- 表示が必要なフレームだけをレンダリングし、直近フレームをキャッシュ
- ウィンドウリサイズ時はデバウンスして再描画し、連続イベントでの負荷を抑制

## 実行方法
1. 依存インストール
```bash
python3 -m pip install -r requirements.txt
```

2. アプリ起動
```bash
python3 app.py
```

## 画面構成
- 左ペイン: ディレクトリ内 GIF 一覧、並び替え、前後ファイル移動
- 右ペイン: 画像表示、再生/停止、フレーム移動、速度変更、フレーム保存
- 下部: ステータス表示（読み込みファイルや保存先）

## 実装ファイル
- `/Users/dai/Documents/repos/gifanimator/app.py`
- `/Users/dai/Documents/repos/gifanimator/requirements.txt`
- `/Users/dai/Documents/repos/gifanimator/docs/gif_animator_app.md`
