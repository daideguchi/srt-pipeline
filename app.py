#!/usr/bin/env python3
"""
SRTFile - 高精度音声同期字幕生成システム UI
StreamlitベースのWebアプリケーション

V9字幕生成エンジンを統合した直感的なユーザーインターフェース
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

def inject_simple_styles():
    """シンプルで確実に見える白背景・黒文字スタイル"""
    css = """
    <style>
    /* 全体の基本設定 - 白背景、黒文字で確実に見える */
    .stApp {
        background-color: #ffffff !important;
        color: #000000 !important;
        font-size: 16px !important;
    }

    /* 全ての要素を確実に黒文字にする */
    .stApp *,
    .stApp p, 
    .stApp span, 
    .stApp label, 
    .stApp div,
    .stApp li, 
    .stApp h1, 
    .stApp h2, 
    .stApp h3,
    .stSidebar *,
    section[data-testid="stSidebar"] *,
    [data-testid="stSidebar"] *,
    [data-testid="stSelectbox"] *,
    [data-testid="stWidgetLabel"],
    [data-testid="stMarkdownContainer"],
    .stSelectbox label,
    .stSelectbox > label,
    .stSelectbox span,
    .stSelectbox div {
        color: #000000 !important;
        opacity: 1 !important;
        background: transparent !important;
        font-weight: 600 !important;
    }
    
    /* サイドバーも確実に白背景にする */
    .stSidebar,
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa !important;
    }

    /* ボタンは青背景・白文字で見やすく */
    .stButton > button, 
    .stDownloadButton > button {
        background-color: #0066cc !important;
        color: #ffffff !important;
        border: 1px solid #0066cc !important;
        border-radius: 8px !important;
        padding: 0.75rem 1rem !important;
        font-weight: 700 !important;
    }

    /* 入力フィールドも白背景・黒文字 */
    textarea, 
    .stTextArea textarea,
    input {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #cccccc !important;
        border-radius: 8px !important;
    }

    /* ファイルアップローダー */
    [data-testid="stFileUploader"] *,
    [data-testid="stFileUploaderDropzone"] *,
    [data-testid="stFileUploadDropzone"] * {
        color: #000000 !important;
        background-color: #f8f9fa !important;
    }

    /* プレースホルダーテキスト */
    input::placeholder, 
    textarea::placeholder {
        color: #666666 !important;
        opacity: 1 !important;
    }

    /* メトリクス（システム情報） */
    [data-testid="stMetric"] {
        background-color: #f8f9fa !important;
        border: 1px solid #cccccc !important;
        border-radius: 8px !important;
        padding: 0.5rem 0.75rem !important;
    }
    
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] {
        color: #000000 !important;
        font-weight: 600 !important;
    }

    /* カスタムクラス */
    .main-header {
        color: #000000 !important;
        text-align: center !important;
        margin: 0 0 1.25rem !important;
        padding: 0 0 0.75rem !important;
        border-bottom: 2px solid #cccccc !important;
        font-size: 2rem !important;
    }
    
    .main-subtitle {
        color: #333333 !important;
        text-align: center !important;
        margin-bottom: 1.5rem !important;
    }

    .status-success { 
        color: #006600 !important; 
        font-weight: 700 !important; 
    }
    
    .status-error { 
        color: #cc0000 !important; 
        font-weight: 700 !important; 
    }
    
    .status-processing { 
        color: #ff6600 !important; 
        font-weight: 700 !important; 
    }

    .file-info {
        background-color: #f0f8ff !important;
        border: 1px solid #cccccc !important;
        border-left: 4px solid #0066cc !important;
        border-radius: 8px !important;
        padding: 0.75rem 1rem !important;
        margin: 0.75rem 0 1rem !important;
        color: #000000 !important;
    }

    .log-container {
        background-color: #f8f9fa !important;
        border: 1px solid #cccccc !important;
        border-radius: 8px !important;
        padding: 0.75rem 1rem !important;
        height: 360px !important;
        overflow-y: auto !important;
        font-family: monospace !important;
        font-size: 0.95rem !important;
        white-space: pre-wrap !important;
        color: #000000 !important;
    }

    /* タブとエキスパンダー */
    [data-testid="stTab"] *,
    [data-testid="stExpander"] * {
        color: #000000 !important;
        opacity: 1 !important;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def main():
    # シンプルなスタイル適用のみ
    inject_simple_styles()
    
    # ヘッダー
    st.markdown('<h1 class="main-header">🎬 SRTFile - 高精度字幕生成システム</h1>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">高速・高精度な字幕生成を直感的に。</div>', unsafe_allow_html=True)

    # サイドバー: ファイルアップロード
    with st.sidebar:
        st.header("📁 ファイルアップロード")
        st.caption("シンプルで確実に見える白背景モード")
        
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
        input_method = st.selectbox(
            "入力方法を選択してください",
            ["📄 ファイルアップロード", "✍️ テキスト貼り付け"],
            index=0
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
    
    with col2:
        st.header("📊 システム情報")
        
        # システム状況
        st.metric("🖥️ Python版", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        st.metric("📁 作業ディレクトリ", f"{Path.cwd().name}")
        st.metric("🕐 現在時刻", datetime.now().strftime("%H:%M:%S"))
        
        # V9エンジン状況
        v9_engine_path = Path("scripts/whisperx_subtitle_generator.py")
        if v9_engine_path.exists():
            st.success("✅ V9エンジン利用可能")
        else:
            st.error("❌ V9エンジン未検出")

def process_subtitle_generation(audio_file, script_content: str):
    """字幕生成処理を実行"""
    # タブ構成: 進捗 / ログ / 結果
    progress_tab, log_tab, result_tab = st.tabs(["🕒 進捗", "📜 ログ", "✅ 結果"])

    with progress_tab:
        progress_bar = st.progress(0)
        status_text = st.empty()
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
            status_text.markdown('<span class="status-processing">🔄 処理を開始しています...</span>', unsafe_allow_html=True)
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
                status_text.markdown('<span class="status-processing">🤖 V9エンジンで字幕生成中...</span>', unsafe_allow_html=True)
            
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
                    status_text.markdown('<span class="status-success">✅ 字幕生成完了！</span>', unsafe_allow_html=True)
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
                    status_text.markdown('<span class="status-error">❌ 字幕生成に失敗しました</span>', unsafe_allow_html=True)
                with result_tab:
                    st.error("字幕ファイルの生成に失敗しました。ログを確認してください。")
    
    except Exception as e:
        update_log(f"❌ エラーが発生しました: {str(e)}")
        with progress_tab:
            status_text.markdown('<span class="status-error">❌ エラーが発生しました</span>', unsafe_allow_html=True)
        with log_tab:
            st.error(f"処理中にエラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main()
