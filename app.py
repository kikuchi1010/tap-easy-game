# QR Tap Challenge - Single-file React App (Canvas Previewable)
# -------------------------------------------------------------
# 使い方（最短）
# 1) まずはローカル保存モードで動作確認できます（Supabase不要）。
#    - 右上の「Open in new tab」(プレビュー)で起動
#    - URLに ?pid=YOUR_ID を付けてアクセス（例： .../index.html?pid=TAKAO001 ）
#    - 名前を入力→「10秒チャレンジ開始」→連打→送信→TOP10表示
#
# 2) 本番運用（ランキング共有）したい場合はSupabaseを使用
#    - Supabaseでプロジェクト作成 → Table: scores
#      Columns:
#        id: uuid (default uuid_generate_v4(), PK)
#        player_id: text (unique)
#        name: text
#        best_count: int8
#        updated_at: timestamptz (default now())
#    - RLS(行レベルセキュリティ) ON、Policy: anonがSELECT/UPSERT可（必要最小限）
#    - 下の SUPABASE_URL / SUPABASE_ANON_KEY を貼り付け
#
# 3) チート簡易対策（初期）
#    - タイマーはクライアント側で固定10秒。必要に応じてサーバ側で「更新間隔制限」など追加。
#    - 同一player_idのベストのみ更新。
#
# 4) 司会/スクリーン用
#    - 画面下部のリーダーボードは数秒ごと自動更新（Supabase接続時）。
#
# 5) 拡張のヒント
#    - 大会コード（event_id）列をscoresに追加し、イベント毎のTOP10を出し分け
#    - 管理者用ダッシュボードやCSVエクスポート
#
# -------------------------------------------------------------

import React, { useEffect, useMemo, useRef, useState } from "react";

# ▼ 必要ならSupabaseを使用（未設定なら自動でローカル保存モードに）
const SUPABASE_URL = ""; # 例: "https:#xxxx.supabase.co"
const SUPABASE_ANON_KEY = ""; # 例: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

let supabase = null as any;
async function ensureSupabase() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null;
  if (!supabase) {
    const mod = await import("@supabase/supabase-js");
    supabase = mod.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return supabase;
}

# ▼ ユーティリティ
function getQueryParam(name: string) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

function cls(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}

# ▼ ローカル保存（フォールバック）
const LS_KEY = "qr_tap_scores_v1";

function lsGetAll(): any[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function lsUpsertBest(player_id: string, name: string, count: number) {
  const all = lsGetAll();
  const i = all.findIndex((r: any) => r.player_id === player_id);
  if (i >= 0) {
    if ((all[i].best_count ?? 0) < count) {
      all[i].best_count = count;
      all[i].name = name;
      all[i].updated_at = new Date().toISOString();
    }
  } else {
    all.push({ player_id, name, best_count: count, updated_at: new Date().toISOString() });
  }
  localStorage.setItem(LS_KEY, JSON.stringify(all));
}

function lsTop10(): any[] {
  const all = lsGetAll();
  return all
    .sort((a: any, b: any) => (b.best_count ?? 0) - (a.best_count ?? 0) || (new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()))
    .slice(0, 10);
}

# ▼ Supabase保存
async function sbUpsertBest(player_id: string, name: string, count: number) {
  const sb = await ensureSupabase();
  if (!sb) {
    lsUpsertBest(player_id, name, count);
    return { ok: true, mode: "local" } as const;
  }

  # 既存取得
  const { data: rows, error: e1 } = await sb
    .from("scores")
    .select("player_id, name, best_count")
    .eq("player_id", player_id)
    .limit(1);
  if (e1) {
    console.error(e1);
    # フォールバック
    lsUpsertBest(player_id, name, count);
    return { ok: false, mode: "fallback-local", error: e1 } as const;
  }

  const currentBest = rows?.[0]?.best_count ?? 0;
  if (count > currentBest) {
    const payload = { player_id, name, best_count: count, updated_at: new Date().toISOString() };
    const { error: e2 } = await sb.from("scores").upsert(payload, { onConflict: "player_id" });
    if (e2) {
      console.error(e2);
      lsUpsertBest(player_id, name, count);
      return { ok: false, mode: "fallback-local", error: e2 } as const;
    }
  }
  return { ok: true, mode: "supabase" } as const;
}

async function sbTop10(): Promise<any[]> {
  const sb = await ensureSupabase();
  if (!sb) return lsTop10();
  const { data, error } = await sb
    .from("scores")
    .select("player_id, name, best_count, updated_at")
    .order("best_count", { ascending: false })
    .order("updated_at", { ascending: true })
    .limit(10);
  if (error) {
    console.error(error);
    return lsTop10();
  }
  return data ?? [];
}

# ▼ メインUI
export default function App() {
  const [playerId, setPlayerId] = useState<string>(getQueryParam("pid") || "");
  const [name, setName] = useState<string>("");
  const [isReady, setReady] = useState<boolean>(false);
  const [isCounting, setCounting] = useState<boolean>(false);
  const [seconds, setSeconds] = useState<number>(10);
  const [remain, setRemain] = useState<number>(10);
  const [count, setCount] = useState<number>(0);
  const [submitted, setSubmitted] = useState<boolean>(false);
  const [top10, setTop10] = useState<any[]>([]);
  const [backendMode, setBackendMode] = useState<string>(SUPABASE_URL && SUPABASE_ANON_KEY ? "supabase" : "local");

  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    # 初期ロード時TOP10
    refreshTop10();
    # Supabaseなら2秒毎に自動更新（司会用）
    let int: any;
    if (backendMode === "supabase") {
      int = setInterval(() => refreshTop10(), 2000);
    }
    return () => int && clearInterval(int);
  }, [backendMode]);

  async function refreshTop10() {
    const rows = await sbTop10();
    setTop10(rows);
  }

  function handleStart() {
    if (!playerId || !name) return alert("プレイヤーIDと名前を入力してください（QRのpid＆名前）");
    setCount(0);
    setRemain(seconds);
    setCounting(true);
    setSubmitted(false);
    const start = Date.now();
    timerRef.current = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - start) / 1000);
      const left = Math.max(0, seconds - elapsed);
      setRemain(left);
      if (left <= 0) {
        window.clearInterval(timerRef.current!);
        setCounting(false);
      }
    }, 100);
  }

  async function handleSubmit() {
    if (isCounting) return;
    const res = await sbUpsertBest(playerId, name, count);
    setSubmitted(true);
    await refreshTop10();
    setBackendMode(res.mode.includes("supabase") ? "supabase" : backendMode);
  }

  const ready = useMemo(() => !!playerId && !!name, [playerId, name]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="max-w-3xl mx-auto p-4">
        <header className="py-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold">QR Tap Challenge</h1>
          <span className={cls("text-xs px-2 py-1 rounded", backendMode === "supabase" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700")}
            title={backendMode === "supabase" ? "Supabase接続中（共有ランキング）" : "ローカル保存（端末内のみ）"}
          >{backendMode === "supabase" ? "ONLINE" : "LOCAL"}</span>
        </header>

        {/* 設定/参加セクション */}
        <section className="bg-white rounded-2xl shadow p-4 mb-6">
          <div className="grid md:grid-cols-3 gap-4">
            <div className="md:col-span-1">
              <label className="block text-sm font-medium">プレイヤーID（QRのpid）</label>
              <input value={playerId} onChange={e => setPlayerId(e.target.value)} placeholder="例: TAKAO001" className="mt-1 w-full rounded-xl border px-3 py-2" />
              <p className="text-xs text-slate-500 mt-1">※QRに「?pid=XXX」を埋め込むと自動入力されます</p>
            </div>
            <div className="md:col-span-1">
              <label className="block text-sm font-medium">名前</label>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="例: たかお" className="mt-1 w-full rounded-xl border px-3 py-2" />
            </div>
            <div className="md:col-span-1">
              <label className="block text-sm font-medium">制限時間（秒）</label>
              <input type="number" min={3} max={60} value={seconds} onChange={e => setSeconds(parseInt(e.target.value || "10", 10))} className="mt-1 w-full rounded-xl border px-3 py-2" />
              <p className="text-xs text-slate-500 mt-1">※初期値10秒</p>
            </div>
          </div>

          <div className="mt-4 flex gap-3 items-center">
            <button onClick={handleStart} className={cls("px-4 py-2 rounded-xl text-white", ready ? "bg-indigo-600 hover:bg-indigo-700" : "bg-slate-300 cursor-not-allowed")} disabled={!ready}>
              {isCounting ? "計測中..." : "10秒チャレンジ開始"}
            </button>
            <span className="text-sm text-slate-600">残り：<b>{remain}</b>s　/　現在：<b>{count}</b>回</span>
          </div>
        </section>

        {/* タップエリア */}
        <section className="bg-white rounded-2xl shadow p-6 mb-6 text-center select-none">
          <p className="text-sm text-slate-600 mb-3">中央の大ボタンを連打してください</p>
          <button
            onClick={() => isCounting && setCount(v => v + 1)}
            className={cls(
              "w-full h-48 md:h-64 rounded-2xl font-bold text-3xl md:text-5xl active:scale-95 transition",
              isCounting ? "bg-rose-500 text-white" : "bg-slate-200 text-slate-500"
            )}
            disabled={!isCounting}
          >{isCounting ? "TAP!" : "待機中"}</button>

          <div className="mt-4">
            <button onClick={handleSubmit} disabled={isCounting || !ready} className={cls("px-4 py-2 rounded-xl text-white", (isCounting || !ready) ? "bg-slate-300 cursor-not-allowed" : "bg-emerald-600 hover:bg-emerald-700")}>結果を送信</button>
            {submitted && <span className="ml-3 text-emerald-700 text-sm">送信しました。ランキングに反映されます。</span>}
          </div>
        </section>

        {/* リーダーボード */}
        <section className="bg-white rounded-2xl shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold">TOP 10 ランキング</h2>
            <button onClick={refreshTop10} className="text-sm px-3 py-1 rounded-lg bg-slate-100 hover:bg-slate-200">更新</button>
          </div>

          <ol className="divide-y">
            {top10.length === 0 && (
              <p className="text-sm text-slate-500">まだ記録がありません</p>
            )}
            {top10.map((r: any, i: number) => (
              <li key={r.player_id} className="flex items-center justify-between py-2">
                <div className="flex items-center gap-3">
                  <span className="w-8 text-center font-bold">{i + 1}</span>
                  <div>
                    <div className="font-medium">{r.name || "???"}</div>
                    <div className="text-xs text-slate-500">ID: {r.player_id}</div>
                  </div>
                </div>
                <div className="text-lg font-bold tabular-nums">{r.best_count ?? r.count} 回</div>
              </li>
            ))}
          </ol>

          <p className="text-xs text-slate-500 mt-4">並び順：回数降順→同数は更新が早い順</p>
        </section>

        {/* 補助：QRの考え方 */}
        <section className="mt-6 text-xs text-slate-500">
          <details>
            <summary className="cursor-pointer">QR設計のTips（クリックで展開）</summary>
            <ul className="list-disc pl-5 mt-2 space-y-1">
              <li>各参加者に一意のpidを配布（印刷物や画面掲示で）例：?pid=TEAM01_001</li>
              <li>同じ端末で複数人が参加する場合は、都度URL（pid）を切り替える運用に。</li>
              <li>大会ごとに集計を分けたい場合は、scoresにevent_id列を追加しURLにも ?event=2025-11-A などを付与。</li>
              <li>不正抑止：極端な連打間隔や異常な連投の自動検知は後追いで追加可能。</li>
            </ul>
          </details>
        </section>
      </div>
    </div>
  );
}
