import streamlit as st
from supabase import create_client, Client
import os
from datetime import datetime
import time

# --- Supabase 接続 ---
SUPABASE_URL = st.secrets["https://cmneviikjxrjxqsvektg.supabase.co"]
SUPABASE_ANON_KEY = st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNtbmV2aWlranhyanhxc3Zla3RnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjIzOTcxNjcsImV4cCI6MjA3Nzk3MzE2N30.GScLcmiZuzEGxKvsFepJTDMi8D33D9MNi6za4RPdebo"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

TABLE_NAME = "score_tap_easy_game"   # ←ここ重要

st.set_page_config(page_title="QR TAP GAME", layout="centered")

# --- セッション初期化 ---
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "count" not in st.session_state:
    st.session_state.count = 0
if "time_left" not in st.session_state:
    st.session_state.time_left = 10

st.title("🎮 QR Tap Challenge")

player_id = st.text_input("プレイヤーID（QRのpid）")
name = st.text_input("名前")
limit_sec = st.number_input("制限時間（秒）", min_value=3, max_value=60, value=10)

col = st.columns(2)
start_btn = col[0].button("10秒チャレンジ開始")

if start_btn:
    if not player_id or not name:
        st.warning("プレイヤーIDと名前は必須です")
    else:
        st.session_state.is_running = True
        st.session_state.count = 0
        st.session_state.time_left = limit_sec
        start_time = time.time()
        while st.session_state.time_left > 0:
            st.session_state.time_left = limit_sec - int(time.time() - start_time)
            st.rerun()  # ← 最新API

# --- TAP ボタン ---
if st.session_state.is_running:
    if st.button("TAP!", use_container_width=True):
        st.session_state.count += 1
    st.metric("残り時間", st.session_state.time_left)
    st.metric("現在の回数", st.session_state.count)
else:
    st.metric("記録", st.session_state.count)

# --- 結果送信 ---
if st.button("結果を送信", disabled=st.session_state.is_running or st.session_state.count == 0):
    # 既存記録を取得
    res = supabase.table(TABLE_NAME).select("*").eq("player_id", player_id).execute()
    old = res.data[0] if res.data else None

    # ベスト更新なら upsert
    best = st.session_state.count
    if old and old["best_count"] >= best:
        pass  # 更新不要
    else:
        supabase.table(TABLE_NAME).upsert({
            "player_id": player_id,
            "name": name,
            "best_count": best,
            "updated_at": datetime.utcnow().isoformat()
        }).execute()

    st.success("✅ 記録を送信しました！")
    st.rerun()

st.write("---")

# --- ランキング表示 ---
st.subheader("🏆 TOP10 ランキング")
ranking = supabase.table(TABLE_NAME).select("*").order("best_count", desc=True).limit(10).execute().data

for i, row in enumerate(ranking, 1):
    st.write(f"{i}. **{row['name']}** — {row['best_count']}回  (ID: {row['player_id']})")
