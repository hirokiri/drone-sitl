# Gemini CLIによる自動実装

## 概要
Issue #7の実装です。IssueからGeminiにアサインすることで自動でGemini CLIがドラフトPRを作成するGitHub Actionsワークフローを追加しました。

## 実装内容
- `.github/workflows/gemini-auto-implementation.yml` ファイルを追加
- Issue がアサインされたときにトリガー
- Gemini API（`GEMINI_API_KEY` シークレット）を使用して実装コード生成
- 生成されたコードを含むドラフトPRを自動作成
- Issueへのコメント通知機能

## 関連Issue
Closes #7

## 設定方法
リポジトリのシークレット設定で `GEMINI_API_KEY` を追加してください。

## 動作確認
- Issue をアサインするとワークフローが自動実行されます
- ドラフトPRが作成され、Issueにコメント通知が届きます
