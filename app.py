import time
import os
from datetime import datetime, timezone
import streamlit as st

# ---------------------------
#  環境設定（Secrets / 環境変数）
# ---------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_ANON_KEY", ""))

# ここでテーブル名を固定（必要なら Secrets/TOML 側で上書き可能）
TABLE_NAME = st.secrets.get("TABLE_NAME", os.environ.get("TABLE_NAME", "score_tap_easy_game"))

sb = None
if SUPABASE_URL and SUPABASE_ANON_KEY:
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ---------------------------
# 初期状態
# ---------------------------
st.set_page_config(page_title="QR Tap Challenge", page_icon="🎮", layout="centered")

params = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
pid = params.get("pid", [""])[0] if isinstance(params.get("pid"), list) else params.get("pid", "")

if "player_id" not in st.session_state:
    st.session_state.player_id = pid or ""
if "name" not in st.session_state:
    st.session_state.name = ""
if "game_seconds" not in st.session_state:
    st.session_state.game_seconds = 10
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "end_ts" not in st.session_state:
    st.session_state.end_ts = 0.0
if "count" not in st.session_state:
    st.session_state.count = 0
if "submitted" not in st.session_state:
    st.session_state.submitted = False

# ---------------------------
# ロジック
# ---------------------------
def start_game():
    if not st.session_state.player_id or not st.session_state.name:
        st.error("プレイヤーIDと名前を入力してください")
        return
    st.session_state.count = 0
    st.session_state.submitted = False
    st.session_state.is_running = True
    st.session_state.end_ts = time.time() + int(st.session_state.game_seconds)

def remain_seconds():
    return max(0, int(st.session_state.end_ts - time.time())) if st.session_state.is_running else 0

def stop_if_timeup():
    if st.session_state.is_running and time.time() >= st.session_state.end_ts:
        st.session_state.is_running = False

def tap_once():
    if st.session_state.is_running:
        st.session_state.count += 1

def save_score(player_id: str, name: str, count: int):
    """自己ベストのみ更新。Supabase未設定時はセッション内ローカルで保持。"""
    if not sb:
        best = st.session_state.get("local_best", {})
        cur = best.get(player_id, {"name": name, "best_count": 0})
        if count > int(cur.get("best_count") or 0):
            best[player_id] = {"name": name, "best_count": count, "updated_at": datetime.now(timezone.utc).isoformat()}
            st.session_state.local_best = best
        return

    # 既存ベストを取得
    res = sb.table(TABLE_NAME).select("best_count").eq("player_id", player_id).limit(1).execute()
    cur_best = int(res.data[0]["best_count"]) if (res and res.data) else 0

    # 上回ったときだけUPSERT
    if count > cur_best:
        payload = {
            "player_id": player_id,
            "name": name,
            "best_count": int(count),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        sb.table(TABLE_NAME).upsert(payload, on_conflict="player_id").execute()

def fetch_top10():
    if not sb:
        best = st.session_state.get("local_best", {})
        rows = [{"player_id": k, "name": v.get("name",""), "best_count": v.get("best_count",0), "updated_at": v.get("updated_at","")}
                for k, v in best.items()]
        rows.sort(key=lambda r: (-int(r["best_count"] or 0), r.get("updated_at","")))
        return rows[:10]

    res = sb.table(TABLE_NAME).select("player_id,name,best_count,updated_at") \
            .order("best_count", desc=True).order("updated_at", desc=False).limit(10).execute()
    return res.data or []

# ---------------------------
# UI
# ---------------------------
st.title("🎮 QR Tap Challenge")

mode_badge = "ONLINE (Supabase)" if sb else "LOCAL (この端末のみ)"
st.caption(f"モード: {mode_badge} / テーブル: {TABLE_NAME}")

with st.form("settings_form"):
    st.text_input("プレイヤーID（QRのpid）", key="player_id", placeholder="例: TEAM01_001")
    st.text_input("名前", key="name", placeholder="例: たかお")
    st.number_input("制限時間（秒）", min_value=3, max_value=60, key="game_seconds")
    st.form_submit_button("10秒チャレンジ開始", on_click=start_game)

stop_if_timeup()
st.write(f"**残り: {remain_seconds()} 秒 / 現在: {st.session_state.count} 回**")

if st.button("TAP!", use_container_width=True, disabled=not st.session_state.is_running):
    tap_once()
    st.rerun()

col1, col2 = st.columns([1,2])
with col1:
    if st.button("結果を送信", disabled=st.session_state.is_running):
        save_score(st.session_state.player_id.strip(), st.session_state.name.strip(), int(st.session_state.count))
        st.session_state.submitted = True
        st.rerun()
with col2:
    if st.session_state.submitted:
        st.success("送信しました。ランキングに反映されます。")

st.markdown("---")
st.subheader("🏆 TOP 10 ランキング")
for i, r in enumerate(fetch_top10(), start=1):
    st.write(f"{i:>2}. **{r.get('name') or '???'}** — {int(r.get('best_count') or 0)} 回 (ID: `{r.get('player_id')}`)")

st.caption("並び順：回数降順→同数は更新が早い順")
