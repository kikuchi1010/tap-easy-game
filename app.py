import time
import os
from datetime import datetime, timezone
import streamlit as st

# ---------------------------
#  Supabase 設定（あとで貼り替える）
# ---------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "")

sb = None
if SUPABASE_URL and SUPABASE_ANON_KEY:
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ---------------------------
# ゲームロジック
# ---------------------------
st.set_page_config(page_title="QR Tap Challenge", page_icon="🎮", layout="centered")

# Queryパラメータから pid 取得
params = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
player_id = params.get("pid", [""])[0] if isinstance(params.get("pid"), list) else params.get("pid", "")
if "player_id" not in st.session_state:
    st.session_state.player_id = player_id

if "name" not in st.session_state:
    st.session_state.name = ""

if "game_seconds" not in st.session_state:
    st.session_state.game_seconds = 10

if "is_running" not in st.session_state:
    st.session_state.is_running = False

if "end_ts" not in st.session_state:
    st.session_state.end_ts = 0

if "count" not in st.session_state:
    st.session_state.count = 0

if "submitted" not in st.session_state:
    st.session_state.submitted = False


def start_game():
    if not st.session_state.player_id or not st.session_state.name:
        st.error("プレイヤーIDと名前を入力してください")
        return
    st.session_state.count = 0
    st.session_state.submitted = False
    st.session_state.is_running = True
    st.session_state.end_ts = time.time() + int(st.session_state.game_seconds)


def remain():
    return max(0, int(st.session_state.end_ts - time.time())) if st.session_state.is_running else 0


def tap():
    if st.session_state.is_running:
        st.session_state.count += 1


def stop_if_finished():
    if st.session_state.is_running and time.time() >= st.session_state.end_ts:
        st.session_state.is_running = False


def save_score(player_id, name, count):
    if not sb:
        if "local_scores" not in st.session_state:
            st.session_state.local_scores = {}
        best = st.session_state.local_scores.get(player_id, 0)
        if count > best:
            st.session_state.local_scores[player_id] = count
        return

    data = sb.table("scores").select("best_count").eq("player_id", player_id).execute()
    best = data.data[0]["best_count"] if data.data else 0

    if count > best:
        sb.table("scores").upsert({
            "player_id": player_id,
            "name": name,
            "best_count": count,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).execute()


def get_top10():
    if not sb:
        if "local_scores" not in st.session_state:
            return []
        return sorted(
            [{"player_id": pid, "name": pid, "best_count": score} for pid, score in st.session_state.local_scores.items()],
            key=lambda x: -x["best_count"]
        )[:10]

    res = sb.table("scores").select("player_id,name,best_count").order("best_count", desc=True).limit(10).execute()
    return res.data or []


# ---------------------------
# UI
# ---------------------------

st.title("🎮 QR Tap Challenge")

with st.form("settings"):
    st.text_input("プレイヤーID（QRのpid）", key="player_id")
    st.text_input("名前", key="name")
    st.number_input("制限時間（秒）", 3, 60, key="game_seconds")
    start = st.form_submit_button("10秒チャレンジ開始", on_click=start_game)

stop_if_finished()

st.write(f"残り: **{remain()}** 秒 / 現在: **{st.session_state.count} 回**")

big = st.button("TAP!", disabled=not st.session_state.is_running)
if big:
    tap()
    st.experimental_rerun()

if st.button("結果を送信", disabled=st.session_state.is_running):
    save_score(st.session_state.player_id, st.session_state.name, st.session_state.count)
    st.session_state.submitted = True

if st.session_state.submitted:
    st.success("結果送信しました ✅")

st.markdown("---")
st.subheader("🏆 TOP 10 ランキング")
for i, r in enumerate(get_top10(), 1):
    st.write(f"{i}. **{r['name']}** - {r['best_count']}回 (ID:{r['player_id']})")
