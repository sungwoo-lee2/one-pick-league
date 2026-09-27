
from flask import Flask, render_template, request, jsonify, session, send_file
import sqlite3, random, string, os, io, json, calendar
from datetime import datetime, timedelta

app = Flask(__name__)

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "one-pick-league"})
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-this-secret")
DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "league.db"))

try:
    from pykrx import stock as krxstock
    PYKRX_OK = True
except Exception:
    krxstock = None
    PYKRX_OK = False

try:
    import qrcode
    QRCODE_OK = True
except Exception:
    qrcode = None
    QRCODE_OK = False

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS rooms(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      admin_pin TEXT NOT NULL,
      revealed INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS players(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      room_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      token TEXT NOT NULL,
      points INTEGER NOT NULL DEFAULT 0,
      wins INTEGER NOT NULL DEFAULT 0,
      top3 INTEGER NOT NULL DEFAULT 0,
      weeks INTEGER NOT NULL DEFAULT 0,
      total_return REAL NOT NULL DEFAULT 0,
      streak_positive INTEGER NOT NULL DEFAULT 0,
      best_streak INTEGER NOT NULL DEFAULT 0,
      UNIQUE(room_id, name)
    );
    CREATE TABLE IF NOT EXISTS picks(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      room_id INTEGER NOT NULL,
      player_id INTEGER NOT NULL,
      week_key TEXT NOT NULL,
      ticker TEXT,
      stock_name TEXT NOT NULL,
      reason TEXT,
      start_price REAL,
      end_price REAL,
      submitted_at TEXT NOT NULL,
      UNIQUE(room_id, week_key, stock_name COLLATE NOCASE),
      UNIQUE(player_id, week_key)
    );
    CREATE TABLE IF NOT EXISTS week_status(
      room_id INTEGER NOT NULL,
      week_key TEXT NOT NULL,
      revealed INTEGER NOT NULL DEFAULT 0,
      finalized INTEGER NOT NULL DEFAULT 0,
      finalized_at TEXT,
      PRIMARY KEY(room_id, week_key)
    );
    CREATE TABLE IF NOT EXISTS history(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      room_id INTEGER NOT NULL,
      week_key TEXT NOT NULL,
      results_json TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()

def room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def player_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=24))

def week_key_for(d=None):
    d = d or datetime.now()
    year, week, _ = (d + timedelta(days=1) if d.weekday()==6 else d).isocalendar()
    return f"{year}-W{week:02d}"

def month_key_for(d=None):
    d = d or datetime.now()
    return d.strftime("%Y-%m")

def get_room(code):
    conn = db()
    r = conn.execute("SELECT * FROM rooms WHERE code=?", (code.upper(),)).fetchone()
    conn.close()
    return r

def ensure_week(room_id, week_key):
    conn = db()
    conn.execute("""INSERT OR IGNORE INTO week_status(room_id,week_key,revealed,finalized)
                    VALUES(?,?,0,0)""", (room_id, week_key))
    conn.commit()
    conn.close()

def calc_return(start, end):
    if not start or not end:
        return None
    return (end/start - 1) * 100

def is_admin(room):
    return session.get(f"admin_{room['code']}") is True

def nearest_friday(d):
    days = (d.weekday() - 4) % 7
    return d - timedelta(days=days)

def ymd(d):
    return d.strftime("%Y%m%d")

def fetch_close(ticker, date_obj):
    if not PYKRX_OK or not ticker:
        return None
    try:
        start = date_obj - timedelta(days=7)
        df = krxstock.get_market_ohlcv_by_date(ymd(start), ymd(date_obj), ticker)
        if df is None or df.empty:
            return None
        return float(df.iloc[-1]["종가"])
    except Exception:
        return None

def badge_for(player, history_results):
    badges=[]
    if player["wins"] >= 3:
        badges.append("👑 3회 우승")
    if player["top3"] >= 5:
        badges.append("🏅 TOP3 단골")
    if player["best_streak"] >= 3:
        badges.append("🔥 3주 연속 플러스")
    if player["weeks"] >= 10:
        badges.append("🎖 10주 참가")
    if history_results:
        last = history_results[0]
        if last.get("rank")==1 and last.get("previous_rank") and last["previous_rank"] >= 4:
            badges.append("🚀 대역전")
    return badges

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/room/<code>")
def room_page(code):
    room = get_room(code)
    if not room:
        return "방을 찾을 수 없습니다.", 404
    return render_template("room.html", code=code.upper())

@app.get("/room/<code>/qr")
def room_qr(code):
    room = get_room(code)
    if not room:
        return "방이 없습니다.", 404
    if not QRCODE_OK:
        return "qrcode 패키지가 필요합니다.", 500
    url = request.host_url.rstrip("/") + f"/room/{code.upper()}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", download_name=f"{code}_qr.png")

@app.post("/api/rooms")
def create_room():
    data = request.get_json(force=True)
    name = (data.get("name") or "주식모임").strip()[:40]
    pin = (data.get("pin") or "1234").strip()[:12]
    conn = db()
    while True:
        code = room_code()
        try:
            cur = conn.execute("INSERT INTO rooms(code,name,admin_pin,created_at) VALUES(?,?,?,?)",
                         (code, name, pin, datetime.now().isoformat()))
            conn.commit()
            room_id = cur.lastrowid
            break
        except sqlite3.IntegrityError:
            pass
    conn.close()
    ensure_week(room_id, week_key_for())
    return jsonify({"code":code, "url":f"/room/{code}"})

@app.post("/api/rooms/<code>/admin-login")
def admin_login(code):
    room = get_room(code)
    if not room:
        return jsonify({"error":"방이 없습니다."}),404
    data=request.get_json(force=True)
    if str(data.get("pin","")) != room["admin_pin"]:
        return jsonify({"error":"방장 PIN이 올바르지 않습니다."}),403
    session[f"admin_{room['code']}"] = True
    return jsonify({"ok":True})

@app.post("/api/rooms/<code>/join")
def join_room(code):
    room = get_room(code)
    if not room:
        return jsonify({"error":"방이 없습니다."}),404
    data=request.get_json(force=True)
    name=(data.get("name") or "").strip()[:20]
    if not name:
        return jsonify({"error":"이름을 입력하세요."}),400
    conn=db()
    existing=conn.execute("SELECT * FROM players WHERE room_id=? AND name=?",
                          (room["id"],name)).fetchone()
    if existing:
        pid=existing["id"]
    else:
        try:
            cur=conn.execute("INSERT INTO players(room_id,name,token) VALUES(?,?,?)",
                             (room["id"],name,player_token()))
            conn.commit(); pid=cur.lastrowid
        except sqlite3.IntegrityError:
            conn.close(); return jsonify({"error":"같은 이름이 있습니다."}),400
    conn.close()
    session["player_id"]=pid
    session["room_code"]=code.upper()
    return jsonify({"ok":True})

@app.get("/api/rooms/<code>/stocks")
def stock_search(code):
    q=(request.args.get("q") or "").strip()
    if len(q)<1:
        return jsonify({"items":[]})
    if not PYKRX_OK:
        return jsonify({"items":[],"warning":"pykrx를 사용할 수 없습니다."})
    try:
        today=ymd(nearest_friday(datetime.now()))
        items=[]
        for market in ("KOSPI","KOSDAQ"):
            tickers=krxstock.get_market_ticker_list(today, market=market)
            for t in tickers:
                name=krxstock.get_market_ticker_name(t)
                if q.lower() in name.lower() or q in t:
                    items.append({"ticker":t,"name":name,"market":market})
                    if len(items)>=20: break
            if len(items)>=20: break
        return jsonify({"items":items})
    except Exception:
        return jsonify({"items":[],"warning":"종목 검색에 실패했습니다."})

@app.get("/api/rooms/<code>/state")
def state(code):
    room=get_room(code)
    if not room: return jsonify({"error":"방이 없습니다."}),404
    week=week_key_for()
    ensure_week(room["id"], week)
    conn=db()
    players=conn.execute("SELECT * FROM players WHERE room_id=? ORDER BY id",(room["id"],)).fetchall()
    picks=conn.execute("SELECT * FROM picks WHERE room_id=? AND week_key=?",(room["id"],week)).fetchall()
    status=conn.execute("SELECT * FROM week_status WHERE room_id=? AND week_key=?",(room["id"],week)).fetchone()
    history_rows=conn.execute("SELECT week_key,results_json FROM history WHERE room_id=? ORDER BY id DESC LIMIT 12",(room["id"],)).fetchall()
    pickmap={p["player_id"]:p for p in picks}
    out=[]; ranking=[]
    for p in players:
        pk=pickmap.get(p["id"])
        ret=calc_return(pk["start_price"],pk["end_price"]) if pk else None
        row={
            "id":p["id"],"name":p["name"],"submitted":bool(pk),
            "ticker":pk["ticker"] if pk and status["revealed"] else None,
            "stock":pk["stock_name"] if pk and status["revealed"] else None,
            "reason":pk["reason"] if pk else None,
            "start":pk["start_price"] if pk else None,
            "end":pk["end_price"] if pk else None,
            "ret":ret,"points":p["points"],"wins":p["wins"],"top3":p["top3"],
            "weeks":p["weeks"],"avg_return":(p["total_return"]/p["weeks"] if p["weeks"] else None),
            "streak":p["streak_positive"],"best_streak":p["best_streak"]
        }
        out.append(row)
        if pk: ranking.append(row.copy())
    ranking.sort(key=lambda x: -999 if x["ret"] is None else x["ret"], reverse=True)
    hist=[]
    monthly={}
    for r in history_rows:
        arr=json.loads(r["results_json"])
        hist.append({"week":r["week_key"],"results":arr})
        mk=r["week_key"][:7] if len(r["week_key"])>=7 else r["week_key"]
        monthly.setdefault(mk,{})
        for x in arr:
            monthly[mk].setdefault(x["name"],0)
            monthly[mk][x["name"]] += x.get("points_awarded",0)
    monthly_champs=[]
    for mk, vals in monthly.items():
        if vals:
            winner=max(vals.items(), key=lambda kv: kv[1])
            monthly_champs.append({"month":mk,"name":winner[0],"points":winner[1]})
    conn.close()
    return jsonify({
        "room":{"code":room["code"],"name":room["name"],"revealed":bool(status["revealed"])},
        "week":week,"finalized":bool(status["finalized"]),
        "players":out,"ranking":ranking,"me":session.get("player_id"),
        "admin":is_admin(room),"pykrx":PYKRX_OK,"qrcode":QRCODE_OK,"history":hist,
        "monthly_champs":monthly_champs[:6],
        "invite_url":request.host_url.rstrip("/") + f"/room/{code.upper()}"
    })

@app.post("/api/rooms/<code>/pick")
def submit_pick(code):
    room=get_room(code)
    if not room:return jsonify({"error":"방이 없습니다."}),404
    pid=session.get("player_id")
    if not pid:return jsonify({"error":"먼저 방에 참가하세요."}),401
    data=request.get_json(force=True)
    ticker=(data.get("ticker") or "").strip()[:12]
    stock=(data.get("stock") or "").strip()[:40]
    reason=(data.get("reason") or "").strip()[:300]
    if not stock:return jsonify({"error":"종목명을 입력하세요."}),400
    week=week_key_for()
    conn=db()
    status=conn.execute("SELECT * FROM week_status WHERE room_id=? AND week_key=?",(room["id"],week)).fetchone()
    if status and status["finalized"]:
        conn.close(); return jsonify({"error":"이번 주차는 이미 마감되었습니다."}),400
    old=conn.execute("SELECT id FROM picks WHERE player_id=? AND week_key=?",(pid,week)).fetchone()
    try:
        if old:
            conn.execute("UPDATE picks SET ticker=?,stock_name=?,reason=?,submitted_at=? WHERE id=?",
                         (ticker,stock,reason,datetime.now().isoformat(),old["id"]))
        else:
            conn.execute("""INSERT INTO picks(room_id,player_id,week_key,ticker,stock_name,reason,submitted_at)
                            VALUES(?,?,?,?,?,?,?)""",
                         (room["id"],pid,week,ticker,stock,reason,datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close(); return jsonify({"error":"이미 다른 참가자가 선택한 종목입니다."}),400
    conn.close()
    return jsonify({"ok":True})

@app.post("/api/rooms/<code>/reveal")
def reveal(code):
    room=get_room(code)
    if not room:return jsonify({"error":"방이 없습니다."}),404
    if not is_admin(room): return jsonify({"error":"방장 권한이 필요합니다."}),403
    conn=db()
    week=week_key_for()
    cp=conn.execute("SELECT COUNT(*) c FROM players WHERE room_id=?",(room["id"],)).fetchone()["c"]
    ck=conn.execute("SELECT COUNT(*) c FROM picks WHERE room_id=? AND week_key=?",(room["id"],week)).fetchone()["c"]
    if cp==0 or ck<cp:
        conn.close();return jsonify({"error":"아직 종목을 제출하지 않은 참가자가 있습니다."}),400
    conn.execute("UPDATE week_status SET revealed=1 WHERE room_id=? AND week_key=?",(room["id"],week))
    conn.commit();conn.close()
    return jsonify({"ok":True})

@app.post("/api/rooms/<code>/auto-prices")
def auto_prices(code):
    room=get_room(code)
    if not room:return jsonify({"error":"방이 없습니다."}),404
    if not is_admin(room): return jsonify({"error":"방장 권한이 필요합니다."}),403
    if not PYKRX_OK: return jsonify({"error":"pykrx가 설치되어 있지 않습니다."}),400
    week=week_key_for()
    today=datetime.now()
    this_friday = today + timedelta(days=(4 - today.weekday()) % 7)
    prev_friday=this_friday-timedelta(days=7)
    conn=db()
    picks=conn.execute("SELECT * FROM picks WHERE room_id=? AND week_key=?",(room["id"],week)).fetchall()
    updated=0
    for p in picks:
        if not p["ticker"]: continue
        start=fetch_close(p["ticker"], prev_friday)
        end=fetch_close(p["ticker"], this_friday)
        if start is not None or end is not None:
            conn.execute("UPDATE picks SET start_price=COALESCE(?,start_price),end_price=COALESCE(?,end_price) WHERE id=?",
                         (start,end,p["id"]))
            updated += 1
    conn.commit();conn.close()
    return jsonify({"ok":True,"updated":updated,"start_date":str(prev_friday.date()),"end_date":str(this_friday.date())})

@app.post("/api/rooms/<code>/prices")
def set_prices(code):
    room=get_room(code)
    if not room:return jsonify({"error":"방이 없습니다."}),404
    if not is_admin(room): return jsonify({"error":"방장 권한이 필요합니다."}),403
    data=request.get_json(force=True)
    pid=int(data.get("player_id"))
    start=data.get("start"); end=data.get("end")
    conn=db()
    conn.execute("""UPDATE picks SET start_price=?,end_price=?
                    WHERE room_id=? AND player_id=? AND week_key=?""",
                 (float(start) if start else None,float(end) if end else None,room["id"],pid,week_key_for()))
    conn.commit();conn.close()
    return jsonify({"ok":True})

@app.post("/api/rooms/<code>/finalize")
def finalize(code):
    room=get_room(code)
    if not room:return jsonify({"error":"방이 없습니다."}),404
    if not is_admin(room): return jsonify({"error":"방장 권한이 필요합니다."}),403
    week=week_key_for()
    conn=db()
    already=conn.execute("SELECT finalized FROM week_status WHERE room_id=? AND week_key=?",(room["id"],week)).fetchone()
    if already and already["finalized"]:
        conn.close();return jsonify({"error":"이미 확정된 주차입니다."}),400
    rows=conn.execute("""SELECT p.id player_id, p.name, p.streak_positive, p.best_streak,
                                k.stock_name, k.start_price, k.end_price
                         FROM players p JOIN picks k ON p.id=k.player_id
                         WHERE p.room_id=? AND k.week_key=?""",(room["id"],week)).fetchall()
    scored=[]
    for r in rows:
        ret=calc_return(r["start_price"],r["end_price"])
        if ret is not None:
            scored.append({"player_id":r["player_id"],"name":r["name"],"stock":r["stock_name"],"ret":ret,
                           "streak_positive":r["streak_positive"],"best_streak":r["best_streak"]})
    if len(scored)<2:
        conn.close();return jsonify({"error":"최소 2명의 시작가/종가가 필요합니다."}),400
    scored.sort(key=lambda x:x["ret"],reverse=True)
    pts=[10,7,5,3,2]
    results=[]
    for i,x in enumerate(scored):
        awarded=(pts[i] if i<len(pts) else 0)+(1 if x["ret"]>0 else 0)
        new_streak=x["streak_positive"]+1 if x["ret"]>0 else 0
        best=max(x["best_streak"],new_streak)
        conn.execute("""UPDATE players SET points=points+?, wins=wins+?, top3=top3+?,
                        weeks=weeks+1,total_return=total_return+?, streak_positive=?, best_streak=?
                        WHERE id=?""",
                     (awarded,1 if i==0 else 0,1 if i<3 else 0,x["ret"],new_streak,best,x["player_id"]))
        results.append({"rank":i+1,"name":x["name"],"stock":x["stock"],"ret":x["ret"],"points_awarded":awarded})
    conn.execute("""UPDATE week_status SET finalized=1, finalized_at=?
                    WHERE room_id=? AND week_key=?""",(datetime.now().isoformat(),room["id"],week))
    conn.execute("INSERT INTO history(room_id,week_key,results_json,created_at) VALUES(?,?,?,?)",
                 (room["id"],week,json.dumps(results,ensure_ascii=False),datetime.now().isoformat()))
    conn.commit();conn.close()
    return jsonify({"ok":True})

@app.post("/api/rooms/<code>/reset-week")
def reset_week(code):
    room=get_room(code)
    if not room:return jsonify({"error":"방이 없습니다."}),404
    if not is_admin(room): return jsonify({"error":"방장 권한이 필요합니다."}),403
    week=week_key_for()
    conn=db()
    conn.execute("DELETE FROM picks WHERE room_id=? AND week_key=?",(room["id"],week))
    conn.execute("UPDATE week_status SET revealed=0,finalized=0,finalized_at=NULL WHERE room_id=? AND week_key=?",(room["id"],week))
    conn.commit();conn.close()
    return jsonify({"ok":True})

init_db()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=os.environ.get("FLASK_DEBUG")=="1")
