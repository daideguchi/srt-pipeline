#!/usr/bin/env python3
"""
SRTFile - 高精度音声同期字幕生成システム UI (macOS可視性問題解決版)
StreamlitベースのWebアプリケーション

V9字幕生成エンジンを統合した直感的なユーザーインターフェース
macOS環境でのチェックボックス/ラベル可視性問題を根本的に解決
"""

import streamlit as st
import tempfile
import os
import subprocess
import sys
import time
import json
from pathlib import Path
import threading
import queue
import io
from datetime import datetime
import streamlit.components.v1 as components

# ページ設定
st.set_page_config(
    page_title="SRTFile - 字幕生成システム",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

def inject_minimal_theming():
    """macOS対応の最小限テーマ設定 - 確実に動作する軽量CSS"""
    css = """
    <style>
    /* 最小限のテーマ設定 - macOS環境で確実に動作 */
    :root {
        --primary-color: #0ea5e9;
        --success-color: #16a34a;
        --warning-color: #f59e0b;
        --danger-color: #dc3545;
        --text-color: #1f2937;
        --bg-color: #ffffff;
        --surface-color: #f8fafc;
        --border-color: #e2e8f0;
    }

    /* ダークモード対応 */
    @media (prefers-color-scheme: dark) {
        :root {
            --text-color: #f1f5f9;
            --bg-color: #0f172a;
            --surface-color: #1e293b;
            --border-color: #334155;
        }
    }

    /* 基本レイアウト */
    .stApp {
        background-color: var(--bg-color);
        color: var(--text-color);
    }

    /* ヘッダースタイル */
    .main-header {
        font-size: 2.5rem;
        color: var(--text-color);
        text-align: center;
        margin: 0 0 1.5rem;
        padding: 0 0 1rem;
        border-bottom: 2px solid var(--border-color);
    }

    .main-subtitle {
        text-align: center;
        color: var(--text-color);
        opacity: 0.8;
        margin-bottom: 2rem;
        font-size: 1.1rem;
    }

    /* ステータス表示 */
    .status-success { 
        color: var(--success-color); 
        font-weight: 700; 
        padding: 0.5rem;
        background: rgba(22, 163, 74, 0.1);
        border-radius: 0.5rem;
        border: 1px solid rgba(22, 163, 74, 0.2);
    }
    
    .status-error { 
        color: var(--danger-color); 
        font-weight: 700; 
        padding: 0.5rem;
        background: rgba(220, 53, 69, 0.1);
        border-radius: 0.5rem;
        border: 1px solid rgba(220, 53, 69, 0.2);
    }
    
    .status-processing { 
        color: var(--warning-color); 
        font-weight: 700; 
        padding: 0.5rem;
        background: rgba(245, 158, 11, 0.1);
        border-radius: 0.5rem;
        border: 1px solid rgba(245, 158, 11, 0.2);
    }

    /* ファイル情報カード */
    .file-info {
        background-color: var(--surface-color);
        border: 1px solid var(--border-color);
        border-left: 4px solid var(--primary-color);
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }

    /* ログコンテナ */
    .log-container {
        background-color: var(--surface-color);
        border: 1px solid var(--border-color);
        border-radius: 0.5rem;
        padding: 1rem;
        height: 360px;
        overflow-y: auto;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 0.9rem;
        white-space: pre-wrap;
        color: var(--text-color);
    }

    /* 設定パネルのスタイル */
    .settings-panel {
        background-color: var(--surface-color);
        border: 1px solid var(--border-color);
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }

    .settings-section {
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid var(--border-color);
    }

    .settings-section:last-child {
        border-bottom: none;
        margin-bottom: 0;
    }

    .settings-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--primary-color);
        margin-bottom: 0.75rem;
    }

    /* ボタンスタイル改善 */
    .stButton > button {
        background: var(--primary-color) !important;
        color: white !important;
        border: none !important;
        border-radius: 0.5rem !important;
        padding: 0.75rem 1.5rem !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }

    .stButton > button:hover {
        filter: brightness(0.9) !important;
        transform: translateY(-1px) !important;
    }

    /* レスポンシブ対応 */
    @media (max-width: 768px) {
        .main-header {
            font-size: 2rem;
        }
        .log-container {
            height: 240px;
        }
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def render_display_settings():
    """表示設定UI - チェックボックスを確実に動作するUIコンポーネントに置き換え"""
    st.header("🎛 表示設定")
    
    # テーマカラー選択
    theme_choice = st.selectbox(
        "🎨 テーマカラー",
        ["オーシャン", "フォレスト", "サンセット", "モノクロ"],
        index=0,
        help="全体のカラーテーマを選択します"
    )
    
    # 文字サイズ設定
    text_size = st.radio(
        "📝 文字サイズ",
        ["標準", "大きめ", "特大"],
        index=1,  # デフォルトは「大きめ」
        horizontal=True,
        help="読みやすさに応じて文字サイズを調整します"
    )
    
    # コントラスト設定
    contrast_mode = st.radio(
        "🔆 コントラスト",
        ["標準", "高コントラスト"],
        index=1,  # デフォルトは「高コントラスト」
        horizontal=True,
        help="見やすさを向上させるコントラスト設定"
    )
    
    # レイアウト設定
    layout_mode = st.radio(
        "📐 レイアウト",
        ["標準", "コンパクト"],
        index=0,  # デフォルトは「標準」
        horizontal=True,
        help="画面の情報密度を調整します"
    )
    
    # 設定サマリー表示
    with st.expander("⚙️ 現在の設定"):
        st.markdown(f"""
        - **テーマ**: {theme_choice}
        - **文字サイズ**: {text_size}
        - **コントラスト**: {contrast_mode}
        - **レイアウト**: {layout_mode}
        """)
    
    st.caption("💡 OS/ブラウザのダークモードに自動対応します")
    
    return {
        'theme': theme_choice,
        'text_size': text_size,
        'contrast': contrast_mode,
        'layout': layout_mode
    }

def render_file_upload_section():
    """ファイルアップロードセクション"""
    st.header("📁 ファイルアップロード")
    
    # 音声ファイル
    st.subheader("🎵 音声ファイル")
    audio_file = st.file_uploader(
        "音声ファイルを選択してください",
        type=['wav', 'm4a', 'mp3', 'flac'],
        help="対応形式: WAV, M4A, MP3, FLAC"
    )
    
    if audio_file is not None:
        st.markdown(f'''
        <div class="file-info">
            <strong>📄 ファイル名:</strong> {audio_file.name}<br>
            <strong>📏 サイズ:</strong> {audio_file.size / 1024 / 1024:.2f} MB<br>
            <strong>🎵 形式:</strong> {audio_file.type}
        </div>
        ''', unsafe_allow_html=True)
    
    st.divider()
    
    # 台本テキスト（ファイル or 貼り付け対応）
    st.subheader("📝 台本テキスト")
    input_method = st.radio(
        "入力方法を選択してください",
        ["📄 ファイルアップロード", "✍️ テキスト貼り付け"],
        horizontal=True
    )
    
    script_content = None
    
    if input_method == "📄 ファイルアップロード":
        script_file = st.file_uploader(
            "台本ファイルを選択してください",
            type=['txt'],
            help="テキストファイル (.txt)"
        )
        
        if script_file is not None:
            # ファイルは一度だけ読み込み、再利用できるよう保存
            raw = script_file.read()
            try:
                script_content = raw.decode('utf-8')
            except Exception:
                script_content = raw.decode('utf-8', errors='ignore')
            
            st.markdown(f'''
            <div class="file-info">
                <strong>📄 ファイル名:</strong> {script_file.name}<br>
                <strong>📏 文字数:</strong> {len(script_content):,} 文字<br>
                <strong>📄 行数:</strong> {len(script_content.splitlines())} 行
            </div>
            ''', unsafe_allow_html=True)
    
    else:  # テキスト貼り付け
        script_content = st.text_area(
            "台本テキストを貼り付けてください",
            height=200,
            help="台本の文章を直接貼り付けることができます",
            placeholder="ここに台本テキストを貼り付けてください..."
        )
        
        if script_content and len(script_content.strip()) > 0:
            st.markdown(f'''
            <div class="file-info">
                <strong>📝 入力方法:</strong> テキスト貼り付け<br>
                <strong>📏 文字数:</strong> {len(script_content):,} 文字<br>
                <strong>📄 行数:</strong> {len(script_content.splitlines())} 行
            </div>
            ''', unsafe_allow_html=True)
    
    # プレビュー（どちらの入力方法でも共通）
    if script_content and len(script_content.strip()) > 0:
        with st.expander("📖 台本プレビュー"):
            preview_text = script_content[:500] + ("..." if len(script_content) > 500 else "")
            st.text_area(
                "内容確認",
                preview_text,
                height=150,
                disabled=True
            )
    
    return audio_file, script_content

def render_system_info():
    """システム情報表示"""
    st.header("📊 システム情報")
    
    # システム状況
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("🖥️ Python版", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        st.metric("📁 作業ディレクトリ", f"{Path.cwd().name}")
    
    with col2:
        st.metric("🕐 現在時刻", datetime.now().strftime("%H:%M:%S"))
        
        # V9エンジン状況
        v9_engine_path = Path("scripts/whisperx_subtitle_generator.py")
        if v9_engine_path.exists():
            st.metric("🚀 V9エンジン", "✅ 利用可能")
        else:
            st.metric("🚀 V9エンジン", "❌ 未検出")

def process_subtitle_generation(audio_file, script_content: str):
    """字幕生成処理を実行"""
    # タブ構成: 進捗 / ログ / 結果
    progress_tab, log_tab, result_tab = st.tabs(["🕒 進捗", "📜 ログ", "✅ 結果"])

    with progress_tab:
        progress_bar = st.progress(0)
        status_container = st.empty()
    with log_tab:
        log_container = st.empty()
    
    # ログ表示用
    log_buffer = []
    
    def update_log(message):
        log_buffer.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        log_text = "\n".join(log_buffer[-20:])  # 最新20行のみ表示
        with log_tab:
            log_container.markdown(f'<div class="log-container">{log_text}</div>', unsafe_allow_html=True)
    
    try:
        with progress_tab:
            status_container.markdown('<div class="status-processing">🔄 処理を開始しています...</div>', unsafe_allow_html=True)
        update_log("字幕生成処理を開始します")
        progress_bar.progress(10)
        
        # 一時ファイル作成
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # 音声ファイル保存
            audio_path = temp_dir / f"audio.{audio_file.name.split('.')[-1]}"
            with open(audio_path, "wb") as f:
                f.write(audio_file.read())
            update_log(f"音声ファイルを保存: {audio_path.name}")
            progress_bar.progress(20)
            
            # 台本ファイル保存（サマリー情報のみ・実処理はUIエンジン側で実施）
            script_path = temp_dir / "script.txt"
            with open(script_path, "w", encoding='utf-8') as f:
                f.write(script_content)
            update_log(f"台本ファイルを保存: {script_path.name}")
            progress_bar.progress(30)
            
            # V9エンジン実行準備
            v9_script = Path("scripts/whisperx_subtitle_generator.py")
            if not v9_script.exists():
                raise FileNotFoundError("V9字幕生成エンジンが見つかりません")
            
            update_log("V9字幕生成エンジンを実行中...")
            progress_bar.progress(40)
            
            # V9エンジン実行（UI統合版）
            with progress_tab:
                status_container.markdown('<div class="status-processing">🤖 V9エンジンで字幕生成中...</div>', unsafe_allow_html=True)
            
            # UI統合エンジンを使用
            from ui_engine import SubtitleGeneratorUI
            
            engine = SubtitleGeneratorUI(log_callback=update_log)
            
            # 字幕生成実行
            success, srt_path, vtt_path, message = engine.generate_subtitles(
                audio_file.getvalue(),
                audio_file.name,
                script_content
            )
            
            if success:
                update_log("✅ V9エンジン実行完了")
                progress_bar.progress(80)
            else:
                update_log(f"❌ V9エンジンエラー: {message}")
                raise Exception(message)
            
            progress_bar.progress(90)
            
            # 結果ファイル確認
            output_srt = Path("subs/final_complete.srt")
            output_vtt = Path("subs/final_complete.vtt")
            
            if output_srt.exists() and output_vtt.exists():
                update_log("✅ 字幕ファイル生成完了")
                with progress_tab:
                    status_container.markdown('<div class="status-success">✅ 字幕生成完了！</div>', unsafe_allow_html=True)
                    progress_bar.progress(100)
                
                # ダウンロード機能
                with result_tab:
                    st.success("🎉 字幕ファイルが正常に生成されました！")
                    d1, d2 = st.columns(2)
                    with d1:
                        with open(output_srt, 'rb') as f:
                            st.download_button(
                                label="📥 SRT形式ダウンロード",
                                data=f.read(),
                                file_name="generated_subtitles.srt",
                                mime="text/plain",
                                use_container_width=True,
                            )
                    with d2:
                        with open(output_vtt, 'rb') as f:
                            st.download_button(
                                label="📥 VTT形式ダウンロード",
                                data=f.read(),
                                file_name="generated_subtitles.vtt",
                                mime="text/plain",
                                use_container_width=True,
                            )

                    # 結果プレビュー
                    with st.expander("📖 生成された字幕プレビュー"):
                        with open(output_srt, 'r', encoding='utf-8') as f:
                            preview_content = f.read()[:1000]
                            st.code(preview_content + "..." if len(preview_content) >= 1000 else preview_content)
                        
            else:
                update_log("❌ 字幕ファイルの生成に失敗しました")
                with progress_tab:
                    status_container.markdown('<div class="status-error">❌ 字幕生成に失敗しました</div>', unsafe_allow_html=True)
                with result_tab:
                    st.error("字幕ファイルの生成に失敗しました。ログを確認してください。")
    
    except Exception as e:
        update_log(f"❌ エラーが発生しました: {str(e)}")
        with progress_tab:
            status_container.markdown('<div class="status-error">❌ エラーが発生しました</div>', unsafe_allow_html=True)
        with log_tab:
            st.error(f"処理中にエラーが発生しました: {str(e)}")

def main():
    """メインアプリケーション"""
    
    # 最小限テーマ注入
    inject_minimal_theming()
    
    # ヘッダー
    st.markdown('<h1 class="main-header">🎬 SRTFile - 高精度字幕生成システム</h1>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">高速・高精度な字幕生成を直感的に。macOS対応版（チェックボックス問題解決済み）</div>', unsafe_allow_html=True)
    
    # サイドバー: 表示設定
    with st.sidebar:
        settings = render_display_settings()
        st.divider()
        audio_file, script_content = render_file_upload_section()
    
    # メインエリア
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("⚙️ 処理コントロール")
        
        # 処理開始ボタン
        can_process = audio_file is not None and script_content is not None and len(script_content.strip()) > 0
        
        if st.button(
            "🚀 字幕生成開始",
            type="primary",
            disabled=not can_process,
            use_container_width=True
        ):
            if can_process:
                process_subtitle_generation(audio_file, script_content)
            else:
                st.error("⚠️ 音声ファイルと台本ファイルの両方をアップロードしてください")
        
        if not can_process:
            st.info("💡 音声ファイルと台本ファイルをアップロードすると処理を開始できます")
        
        # 設定の現在値表示
        with st.expander("🔧 UI設定詳細"):
            st.json(settings)
    
    with col2:
        render_system_info()

if __name__ == "__main__":
    main()