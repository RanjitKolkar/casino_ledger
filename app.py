import streamlit as st
import sqlite3, hashlib, json, uuid, os
from datetime import datetime, date
import pandas as pd
import plotly.express as px

DB = os.getenv("CASINO_DB_PATH", os.path.join(os.path.dirname(__file__), "casino_ledger_v4.db"))


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c


def now(): return datetime.now().isoformat(timespec="seconds")

def fetch(sql, p=()):
    c=db(); rows=c.execute(sql,p).fetchall(); c.close(); return [dict(r) for r in rows]

def one(sql,p=()):
    c=db(); r=c.execute(sql,p).fetchone(); c.close(); return dict(r) if r else None

def scalar(sql,p=()):
    c=db(); r=c.execute(sql,p).fetchone(); c.close(); return r[0] if r else None

def execsql(sql,p=()):
    c=db(); c.execute(sql,p); c.commit(); c.close()

def df(sql,p=()): return pd.DataFrame(fetch(sql,p))


def init():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS players(
      id INTEGER PRIMARY KEY AUTOINCREMENT, player_code TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL, dob TEXT, pan TEXT, mobile TEXT, email TEXT, address TEXT,
      kyc_status TEXT DEFAULT 'PENDING', kyc_ref TEXT, risk_level TEXT DEFAULT 'LOW',
      account_status TEXT DEFAULT 'ACTIVE', self_excluded INTEGER DEFAULT 0, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL, role TEXT NOT NULL, player_id INTEGER);
    CREATE TABLE IF NOT EXISTS token_accounts(id INTEGER PRIMARY KEY AUTOINCREMENT, account_no TEXT UNIQUE NOT NULL,
      player_id INTEGER NOT NULL, status TEXT DEFAULT 'ACTIVE', opened_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS token_types(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL, cashable INTEGER DEFAULT 1, transferable INTEGER DEFAULT 0, redeemable INTEGER DEFAULT 1, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS token_balances(id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL,
      token_type_id INTEGER NOT NULL, balance REAL DEFAULT 0, UNIQUE(account_id,token_type_id));
    CREATE TABLE IF NOT EXISTS token_units(id INTEGER PRIMARY KEY AUTOINCREMENT, serial_no TEXT UNIQUE NOT NULL,
      token_type_id INTEGER, denomination REAL NOT NULL, status TEXT NOT NULL, account_id INTEGER, issued_at TEXT, redeemed_at TEXT);
    CREATE TABLE IF NOT EXISTS games(id INTEGER PRIMARY KEY AUTOINCREMENT, game_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
      game_type TEXT NOT NULL, table_no TEXT, device_no TEXT, min_bet REAL DEFAULT 100, max_bet REAL DEFAULT 1000000,
      progressive INTEGER DEFAULT 0, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT, session_code TEXT UNIQUE NOT NULL,
      game_id INTEGER NOT NULL, table_no TEXT, dealer TEXT, pit_supervisor TEXT, started_at TEXT, ended_at TEXT,
      status TEXT DEFAULT 'OPEN', opening_float REAL DEFAULT 0, closing_float REAL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS rounds(id INTEGER PRIMARY KEY AUTOINCREMENT, round_code TEXT UNIQUE NOT NULL, session_id INTEGER NOT NULL,
      round_no INTEGER, started_at TEXT, ended_at TEXT, status TEXT DEFAULT 'OPEN', result_description TEXT, jackpot_flag INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS bets(id INTEGER PRIMARY KEY AUTOINCREMENT, bet_ref TEXT UNIQUE NOT NULL, round_id INTEGER NOT NULL,
      player_id INTEGER NOT NULL, bet_type TEXT, stake REAL NOT NULL, outcome TEXT, payout REAL DEFAULT 0, share_pct REAL DEFAULT 100,
      side_pot REAL DEFAULT 0, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS payout_allocations(id INTEGER PRIMARY KEY AUTOINCREMENT, payout_ref TEXT UNIQUE NOT NULL,
      round_id INTEGER NOT NULL, player_id INTEGER NOT NULL, source_type TEXT, gross_amount REAL NOT NULL, share_pct REAL DEFAULT 100,
      created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS transfers(id INTEGER PRIMARY KEY AUTOINCREMENT, transfer_ref TEXT UNIQUE NOT NULL,
      from_player_id INTEGER, to_player_id INTEGER, amount REAL NOT NULL, reason TEXT, approved_by TEXT,
      created_at TEXT NOT NULL, status TEXT DEFAULT 'COMPLETED');
    CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, ts TEXT NOT NULL,
      player_id INTEGER, event_type TEXT NOT NULL, amount REAL NOT NULL, balance_before REAL, balance_after REAL,
      game_id INTEGER, session_id INTEGER, round_id INTEGER, token_type TEXT DEFAULT 'CASHABLE', token_id INTEGER,
      counter TEXT, table_no TEXT, reference TEXT, description TEXT, actor TEXT, status TEXT DEFAULT 'POSTED',
      previous_hash TEXT, record_hash TEXT);
    CREATE TABLE IF NOT EXISTS settlement(id INTEGER PRIMARY KEY AUTOINCREMENT, settlement_ref TEXT UNIQUE NOT NULL,
      player_id INTEGER, method TEXT, amount REAL, ledger_event_id TEXT, created_at TEXT, status TEXT, direction TEXT);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT, action TEXT,
      entity TEXT, entity_id TEXT, details TEXT, previous_hash TEXT, record_hash TEXT);
    CREATE TABLE IF NOT EXISTS tax_rules(id INTEGER PRIMARY KEY AUTOINCREMENT, rule_code TEXT UNIQUE NOT NULL,
      effective_from TEXT, effective_to TEXT, rate REAL DEFAULT 0, threshold REAL DEFAULT 0, deduction REAL DEFAULT 0,
      taxable_event_types TEXT NOT NULL, description TEXT, active INTEGER DEFAULT 1, created_at TEXT);
    CREATE TABLE IF NOT EXISTS tax_statements(id INTEGER PRIMARY KEY AUTOINCREMENT, statement_ref TEXT UNIQUE,
      player_id INTEGER, period_from TEXT, period_to TEXT, rule_code TEXT, gross_base REAL, deduction REAL,
      eligible_winnings REAL, tax_amount REAL, net_amount REAL, generated_by TEXT, generated_at TEXT);
    CREATE TABLE IF NOT EXISTS compliance_flags(id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER,
      flag_type TEXT, severity TEXT, description TEXT, source_event TEXT, status TEXT DEFAULT 'OPEN', created_at TEXT);
    CREATE TABLE IF NOT EXISTS casino_config(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS cage_shifts(id INTEGER PRIMARY KEY AUTOINCREMENT, shift_ref TEXT UNIQUE NOT NULL,
      cashier TEXT, opening_float REAL, closing_float REAL, opened_at TEXT, closed_at TEXT, status TEXT DEFAULT 'OPEN');
    CREATE TABLE IF NOT EXISTS comps(id INTEGER PRIMARY KEY AUTOINCREMENT, comp_ref TEXT UNIQUE NOT NULL,
      player_id INTEGER, comp_type TEXT, amount REAL, reason TEXT, issued_by TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS jackpots(id INTEGER PRIMARY KEY AUTOINCREMENT, jackpot_ref TEXT UNIQUE NOT NULL,
      game_id INTEGER, pool_opening REAL DEFAULT 0, contribution REAL DEFAULT 0, trigger_amount REAL DEFAULT 0,
      payout REAL DEFAULT 0, status TEXT DEFAULT 'OPEN', created_at TEXT);
    CREATE TABLE IF NOT EXISTS reversals(id INTEGER PRIMARY KEY AUTOINCREMENT, reversal_ref TEXT UNIQUE NOT NULL,
      original_event_id TEXT, replacement_event_id TEXT, reason TEXT, approved_by TEXT, created_at TEXT);
    """)
    c.commit(); c.close(); seed()


def audit(actor, action, entity, eid, details):
    prev = scalar("SELECT record_hash FROM audit ORDER BY id DESC LIMIT 1") or ""
    ts=now(); raw=f"{prev}|{ts}|{actor}|{action}|{entity}|{eid}|{details}"
    h=hashlib.sha256(raw.encode()).hexdigest()
    execsql("INSERT INTO audit(ts,actor,action,entity,entity_id,details,previous_hash,record_hash) VALUES(?,?,?,?,?,?,?,?)",
            (ts,actor,action,entity,str(eid),details,prev,h))


def account_for(pid):
    return one("SELECT * FROM token_accounts WHERE player_id=? AND status='ACTIVE'", (pid,))


def balance(pid, token_type="CASHABLE"):
    r=one("""SELECT COALESCE(tb.balance,0) b FROM token_balances tb JOIN token_accounts ta ON ta.id=tb.account_id
              JOIN token_types tt ON tt.id=tb.token_type_id WHERE ta.player_id=? AND tt.code=?""", (pid,token_type))
    return float(r["b"] if r else 0)


def post_ledger(pid,event_type,amount,actor,token_type="CASHABLE",game_id=None,session_id=None,round_id=None,
                counter="",table_no="",reference="",description=""):
    c=db();
    try:
        p=c.execute("SELECT id FROM players WHERE id=?",(pid,)).fetchone()
        if not p: raise ValueError("Player not found")
        ta=c.execute("SELECT id FROM token_accounts WHERE player_id=? AND status='ACTIVE'",(pid,)).fetchone()
        tt=c.execute("SELECT id FROM token_types WHERE code=?",(token_type,)).fetchone()
        if not ta or not tt: raise ValueError("Token account/type not found")
        b=c.execute("SELECT balance FROM token_balances WHERE account_id=? AND token_type_id=?",(ta[0],tt[0])).fetchone()
        before=float(b[0] if b else 0); after=before+float(amount)
        if after < -0.000001: raise ValueError(f"Insufficient {token_type} balance: ₹{before:,.2f}")
        prev=c.execute("SELECT record_hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone(); prev=prev[0] if prev else ""
        ts=now(); eid="LED-"+uuid.uuid4().hex[:16].upper()
        raw=json.dumps([eid,ts,pid,event_type,amount,before,after,game_id,session_id,round_id,token_type,counter,table_no,reference,description,actor,prev],separators=(",",":"))
        h=hashlib.sha256(raw.encode()).hexdigest()
        c.execute("""INSERT INTO ledger(event_id,ts,player_id,event_type,amount,balance_before,balance_after,game_id,session_id,round_id,token_type,counter,table_no,reference,description,actor,previous_hash,record_hash)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (eid,ts,pid,event_type,amount,before,after,game_id,session_id,round_id,token_type,counter,table_no,reference,description,actor,prev,h))
        c.execute("INSERT OR IGNORE INTO token_balances(account_id,token_type_id,balance) VALUES(?,?,0)",(ta[0],tt[0]))
        c.execute("UPDATE token_balances SET balance=? WHERE account_id=? AND token_type_id=?",(after,ta[0],tt[0]))
        c.commit()
    except Exception:
        c.rollback(); c.close(); raise
    c.close(); audit(actor,"LEDGER_POST","ledger",eid,f"{event_type};amount={amount};player={pid};token={token_type}"); return eid


def seed():
    if scalar("SELECT COUNT(*) FROM casino_config"):
        return
    t=now()
    configs={
      "casino_name":"Demo Casino", "currency":"INR", "default_cash_token":"CASHABLE",
      "max_single_redemption":"10000000", "max_single_purchase":"10000000",
      "player_transfer_enabled":"0", "require_kyc_for_play":"1", "maker_checker_threshold":"500000"
    }
    for k,v in configs.items(): execsql("INSERT INTO casino_config(key,value) VALUES(?,?)",(k,v))
    token_types=[("CASHABLE","Cashable Casino Value",1,0,1),("BONUS","Bonus / Promotional",0,0,0),
                 ("TOURNAMENT","Tournament Credits",0,0,0),("RESTRICTED","Restricted Value",0,0,0)]
    for x in token_types: execsql("INSERT INTO token_types(code,name,cashable,transferable,redeemable) VALUES(?,?,?,?,?)",x)
    games=[
      ("G001","Royal Roulette","Roulette","R-01","",100,1000000,0),("G002","Blackjack Alpha","Blackjack","BJ-01","",100,500000,0),
      ("G003","Grand Baccarat","Baccarat","BAC-01","",500,1000000,0),("G004","Poker Room","Poker","P-01","",500,1000000,0),
      ("G005","Diamond Slots","Slot Machine","S-01","EGM-01",10,100000,1),("G006","Craps Hall","Craps","CR-01","",100,500000,0),
      ("G007","Sic Bo","Sic Bo","SB-01","",100,250000,0),("G008","Teen Patti","Teen Patti","TP-01","",100,500000,0),
      ("G009","Andar Bahar","Andar Bahar","AB-01","",100,250000,0),("G010","Casino War","Casino War","CW-01","",100,250000,0),
      ("G011","Three Card Poker","Three Card Poker","TCP-01","",100,500000,0),("G012","Caribbean Stud","Caribbean Stud","CS-01","",100,500000,0),
      ("G013","Dragon Tiger","Dragon Tiger","DT-01","",100,250000,0),("G014","Keno","Keno","K-01","",100,250000,0),
      ("G015","Electronic Gaming Machine","Electronic Gaming Machine","EGM-01","EGM-01",10,100000,1),("G016","Progressive Jackpot","Jackpot","JP-01","",100,10000000,1),
      ("G017","Weekend Tournament","Tournament","T-01","",1000,10000000,0),("G018","VIP Roulette","Roulette","R-VIP","",1000,5000000,0),
      ("G019","VIP Baccarat","Baccarat","BAC-VIP","",1000,5000000,0),("G020","Multi Game","Other","MG-01","",100,1000000,0)]
    for x in games: execsql("INSERT INTO games(game_code,name,game_type,table_no,device_no,min_bet,max_bet,progressive) VALUES(?,?,?,?,?,?,?,?)",x)
    for i in range(1,21):
        code=f"PLR-{1000+i}"; name=f"Player {i}"; mobile=f"98{i:08d}"
        execsql("INSERT INTO players(player_code,name,dob,pan,mobile,email,address,kyc_status,kyc_ref,risk_level,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (code,name,"1990-01-01",f"ABCDE{i:04d}F",mobile,f"player{i}@demo.local","Demo Address","VERIFIED",f"KYC-{i:05d}","MEDIUM" if i%7==0 else "LOW",t))
        pid=scalar("SELECT id FROM players WHERE player_code=?",(code,)); execsql("INSERT INTO token_accounts(account_no,player_id,opened_at) VALUES(?,?,?)",(f"TA-{pid:06d}",pid,t))
        for tt in ["CASHABLE","BONUS","TOURNAMENT","RESTRICTED"]:
            tid=scalar("SELECT id FROM token_types WHERE code=?",(tt,)); aid=scalar("SELECT id FROM token_accounts WHERE player_id=?",(pid,)); execsql("INSERT INTO token_balances(account_id,token_type_id,balance) VALUES(?,?,0)",(aid,tid))
    # Explicit demo users Player 1 and Player 2
    execsql("INSERT INTO users(username,password,role,player_id) VALUES('player1','player123','PLAYER',1)")
    execsql("INSERT INTO users(username,password,role,player_id) VALUES('player2','player123','PLAYER',2)")
    execsql("INSERT INTO users(username,password,role,player_id) VALUES('admin','admin123','ADMIN',NULL)")
    execsql("INSERT INTO users(username,password,role,player_id) VALUES('investigator','audit123','INVESTIGATOR',NULL)")
    execsql("INSERT INTO users(username,password,role,player_id) VALUES('cage','cage123','CAGE',NULL)")
    # Default configurable tax rule for demo purposes only.
    taxable=json.dumps(["WINNING","JACKPOT"])
    execsql("INSERT INTO tax_rules(rule_code,effective_from,effective_to,rate,threshold,deduction,taxable_event_types,description,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("DEMO-WINNINGS-30","2026-04-01","2099-03-31",30,0,0,taxable,"Demo rule. Configure/verify applicable Indian tax law before production.",1,t))
    audit("SYSTEM","INITIALIZE","system","1","Casino Ledger v4 initialized with persistent SQLite storage and demo players")


def header():
    st.set_page_config(page_title="Casino Digital Ledger",page_icon="🎰",layout="wide")
    st.markdown("""<style>.main .block-container{max-width:1500px;padding-top:1.5rem}.hero{padding:22px;border-radius:18px;background:linear-gradient(135deg,#111827,#292524);color:white}.hero h1{margin:0}.muted{color:#6b7280}</style>""",unsafe_allow_html=True)
    st.markdown('<div class="hero"><h1>🎰 Casino Digital Ledger</h1><p>Player lifecycle · Digital value · Game events · Cage reconciliation · Investigator audit</p></div>',unsafe_allow_html=True)


def login():
    header(); a,b=st.columns([1,1])
    with a:
        st.subheader("Sign in")
        with st.form("login"):
            u=st.text_input("Username"); p=st.text_input("Password",type="password")
            if st.form_submit_button("Sign in",type="primary"):
                r=one("SELECT * FROM users WHERE username=? AND password=?",(u,p))
                if r: st.session_state.user=r; st.rerun()
                else: st.error("Invalid credentials")
        st.caption("Demo: player1/player123 · player2/player123 · cage/cage123 · admin/admin123 · investigator/audit123")
    with b:
        st.subheader("New Player Registration")
        with st.form("new_player"):
            name=st.text_input("Full name *"); dob=st.date_input("Date of birth",date(1990,1,1)); pan=st.text_input("PAN")
            mobile=st.text_input("Mobile *"); email=st.text_input("Email"); address=st.text_area("Address")
            if st.form_submit_button("Register new player"):
                if not name.strip() or not mobile.strip(): st.error("Name and mobile are required.")
                else:
                    try:
                        code="PLR-"+uuid.uuid4().hex[:8].upper(); ref="KYC-"+uuid.uuid4().hex[:10].upper();
                        execsql("INSERT INTO players(player_code,name,dob,pan,mobile,email,address,kyc_status,kyc_ref,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (code,name,str(dob),pan,mobile,email,address,"PENDING",ref,now()))
                        pid=scalar("SELECT id FROM players WHERE player_code=?",(code,)); execsql("INSERT INTO token_accounts(account_no,player_id,opened_at) VALUES(?,?,?)",("TA-"+uuid.uuid4().hex[:10].upper(),pid,now()))
                        for tt in ["CASHABLE","BONUS","TOURNAMENT","RESTRICTED"]:
                            tid=scalar("SELECT id FROM token_types WHERE code=?",(tt,)); aid=scalar("SELECT id FROM token_accounts WHERE player_id=?",(pid,)); execsql("INSERT INTO token_balances(account_id,token_type_id,balance) VALUES(?,?,0)",(aid,tid))
                        username=code.lower(); password=uuid.uuid4().hex[:8]
                        execsql("INSERT INTO users(username,password,role,player_id) VALUES(?,?,?,?)",(username,password,"PLAYER",pid))
                        audit("SELF_REGISTRATION","PLAYER_REGISTER","player",pid,f"{code};KYC=PENDING")
                        st.success("Registration successful")
                        st.code(f"Username: {username}\nTemporary password: {password}")
                    except sqlite3.IntegrityError: st.error("Registration could not be completed due to a duplicate record.")


def sidebar():
    u=st.session_state.user; st.sidebar.title("🎰 Ledger"); st.sidebar.caption(f"{u['role']} · {u['username']}")
    if st.sidebar.button("Logout"): st.session_state.pop("user"); st.rerun()


def player_portal():
    pid=st.session_state.user["player_id"]; p=one("SELECT * FROM players WHERE id=?",(pid,)); acct=account_for(pid)
    st.title(f"Welcome, {p['name']}")
    c1,c2,c3,c4=st.columns(4); c1.metric("Cashable Tokens",f"₹{balance(pid):,.2f}"); c2.metric("Bonus",f"₹{balance(pid,'BONUS'):,.2f}"); c3.metric("KYC",p['kyc_status']); c4.metric("Status",p['account_status'])
    tabs=st.tabs(["Home","Registration","Buy Tokens","Play","Redeem","Activity"])
    with tabs[0]:
        st.info("Tax information is not available in the Player Portal. Your account shows casino-value balances and operational activity only.")
        st.write(f"Player ID: **{p['player_code']}** · Token account: **{acct['account_no']}**")
        st.dataframe(df("SELECT ts,event_type,amount,token_type,balance_after,reference,description FROM ledger WHERE player_id=? ORDER BY id DESC LIMIT 15",(pid,)),use_container_width=True,hide_index=True)
    with tabs[1]:
        st.subheader("Registration / KYC profile")
        st.write({k:p[k] for k in ['player_code','name','dob','pan','mobile','email','address','kyc_status','kyc_ref','risk_level']})
    with tabs[2]:
        amount=st.number_input("Amount (₹)",min_value=100.0,max_value=float(scalar("SELECT value FROM casino_config WHERE key='max_single_purchase'")),value=5000.0,step=100.0,key="buy")
        method=st.selectbox("Funding method",["Cash Counter","Card","UPI","Bank Transfer"])
        if st.button("Purchase Digital Tokens",type="primary"):
            if p['kyc_status']!="VERIFIED": st.error("KYC must be verified before token purchase in this prototype.")
            else:
                ref="BUY-"+uuid.uuid4().hex[:10].upper(); eid=post_ledger(pid,"TOKEN_ISSUE",amount,"CAGE",reference=ref,description=f"Cashable token issue against {method}")
                execsql("INSERT INTO settlement(settlement_ref,player_id,method,amount,ledger_event_id,created_at,status,direction) VALUES(?,?,?,?,?,?,?,?)",(ref,pid,method,amount,eid,now(),"SETTLED","IN")); audit("CAGE","TOKEN_ISSUE","player",pid,f"{ref};₹{amount};{method}"); st.success(f"Issued ₹{amount:,.2f}. Ref {ref}"); st.rerun()
    with tabs[3]:
        games=df("SELECT * FROM games WHERE active=1 ORDER BY game_type,name")
        gid=st.selectbox("Game",games.id.tolist(),format_func=lambda x: games.loc[games.id==x,'name'].iloc[0]); g=games[games.id==gid].iloc[0]
        st.caption(f"{g.game_type} · {g.table_no or g.device_no} · ₹{g.min_bet:,.0f}–₹{g.max_bet:,.0f}")
        stake=st.number_input("Stake (₹)",min_value=float(g.min_bet),max_value=float(g.max_bet),value=float(g.min_bet),step=100.0)
        result=st.selectbox("Demo result",["LOSS","WIN","DRAW","VOID"]); bet_type=st.selectbox("Bet type",["Main bet","Side bet","Split/Combination","Jackpot contribution","Tournament entry"])
        if st.button("Record Game Round",type="primary"):
            try:
                if p['account_status']!="ACTIVE" or p['self_excluded']: raise ValueError("Player account is not eligible to play.")
                sc="SES-"+uuid.uuid4().hex[:8].upper(); rc="RND-"+uuid.uuid4().hex[:8].upper();
                execsql("INSERT INTO sessions(session_code,game_id,table_no,dealer,started_at,ended_at,status) VALUES(?,?,?,?,?,?,?)",(sc,int(gid),g.table_no,"DEMO",now(),now(),"CLOSED")); sid=scalar("SELECT id FROM sessions WHERE session_code=?",(sc,))
                execsql("INSERT INTO rounds(round_code,session_id,round_no,started_at,ended_at,status,result_description,jackpot_flag) VALUES(?,?,?,?,?,?,?,?)",(rc,sid,1,now(),now(),"CLOSED",result,1 if bet_type=="Jackpot contribution" else 0)); rid=scalar("SELECT id FROM rounds WHERE round_code=?",(rc,))
                bref="BET-"+uuid.uuid4().hex[:10].upper(); post_ledger(pid,"BET",-stake,"GAME",game_id=int(gid),session_id=sid,round_id=rid,table_no=g.table_no,reference=bref,description=bet_type)
                payout=0 if result in ["LOSS","VOID"] else (stake*2 if result=="WIN" else stake)
                if payout: post_ledger(pid,"JACKPOT" if bet_type=="Jackpot contribution" else "WINNING",payout,"GAME_ENGINE",game_id=int(gid),session_id=sid,round_id=rid,table_no=g.table_no,reference=bref,description=f"Result {result}")
                execsql("INSERT INTO bets(bet_ref,round_id,player_id,bet_type,stake,outcome,payout,created_at) VALUES(?,?,?,?,?,?,?,?)",(bref,rid,pid,bet_type,stake,result,payout,now()))
                st.success(f"Round settled: {bref}"); st.rerun()
            except Exception as e: st.error(str(e))
    with tabs[4]:
        amount=st.number_input("Redemption amount (₹)",min_value=100.0,max_value=float(scalar("SELECT value FROM casino_config WHERE key='max_single_redemption'")),value=1000.0,step=100.0,key="redeem")
        method=st.selectbox("Settlement method",["Cash Counter","Bank Transfer","UPI"])
        if st.button("Redeem Cashable Tokens",type="primary"):
            try:
                ref="RED-"+uuid.uuid4().hex[:10].upper(); eid=post_ledger(pid,"TOKEN_REDEMPTION",-amount,"CAGE",reference=ref,description="Cashable token redemption")
                execsql("INSERT INTO settlement(settlement_ref,player_id,method,amount,ledger_event_id,created_at,status,direction) VALUES(?,?,?,?,?,?,?,?)",(ref,pid,method,amount,eid,now(),"PAID","OUT")); audit("CAGE","REDEMPTION","player",pid,f"{ref};₹{amount};{method}"); st.success(f"Redemption completed: {ref}"); st.rerun()
            except Exception as e: st.error(str(e))
    with tabs[5]:
        x=df("SELECT ts,event_type,amount,token_type,balance_before,balance_after,table_no,reference,description,event_id FROM ledger WHERE player_id=? ORDER BY id DESC",(pid,)); st.dataframe(x,use_container_width=True,height=500,hide_index=True); st.download_button("Download activity",x.to_csv(index=False).encode(),"my_activity.csv","text/csv")


def cage_portal():
    st.title("🏦 Cage & Casino Operations")
    st.caption("Registration, funding, token controls, games, rounds and reconciliation. Tax data is not available here.")
    tabs=st.tabs(["Register Player","Players","Token Control","Games","Rounds","Cage Shift","Reconciliation"])
    with tabs[0]:
        with st.form("cage_reg"):
            name=st.text_input("Full name *"); dob=st.date_input("DOB",date(1990,1,1)); pan=st.text_input("PAN"); mobile=st.text_input("Mobile *"); email=st.text_input("Email"); address=st.text_area("Address"); kyc=st.selectbox("KYC",["PENDING","VERIFIED","REJECTED"])
            if st.form_submit_button("Register Player",type="primary"):
                if not name or not mobile: st.error("Name and mobile are required.")
                else:
                    code="PLR-"+uuid.uuid4().hex[:8].upper(); ref="KYC-"+uuid.uuid4().hex[:10].upper(); execsql("INSERT INTO players(player_code,name,dob,pan,mobile,email,address,kyc_status,kyc_ref,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(code,name,str(dob),pan,mobile,email,address,kyc,ref,now())); pid=scalar("SELECT id FROM players WHERE player_code=?",(code,)); execsql("INSERT INTO token_accounts(account_no,player_id,opened_at) VALUES(?,?,?)",("TA-"+uuid.uuid4().hex[:10].upper(),pid,now()));
                    for tt in ["CASHABLE","BONUS","TOURNAMENT","RESTRICTED"]: tid=scalar("SELECT id FROM token_types WHERE code=?",(tt,)); aid=scalar("SELECT id FROM token_accounts WHERE player_id=?",(pid,)); execsql("INSERT INTO token_balances(account_id,token_type_id,balance) VALUES(?,?,0)",(aid,tid))
                    audit("CAGE","PLAYER_REGISTER","player",pid,f"{code};KYC={kyc}"); st.success(f"Registered {code}. Player login can be created by the account desk.")
    with tabs[1]: st.dataframe(df("SELECT player_code,name,pan,mobile,kyc_status,risk_level,account_status,self_excluded,created_at FROM players ORDER BY id DESC"),use_container_width=True)
    with tabs[2]:
        st.dataframe(df("SELECT p.player_code,p.name,tt.code token_type,tb.balance FROM token_balances tb JOIN token_accounts ta ON ta.id=tb.account_id JOIN players p ON p.id=ta.player_id JOIN token_types tt ON tt.id=tb.token_type_id ORDER BY p.id,tt.id"),use_container_width=True)
        st.subheader("Token types")
        st.dataframe(df("SELECT * FROM token_types"),use_container_width=True)
    with tabs[3]: st.dataframe(df("SELECT game_code,name,game_type,table_no,device_no,min_bet,max_bet,progressive,active FROM games ORDER BY game_type,name"),use_container_width=True)
    with tabs[4]: st.dataframe(df("SELECT r.round_code,g.name,g.game_type,s.table_no,r.status,r.result_description,p.player_code,b.bet_type,b.stake,b.outcome,b.payout FROM rounds r JOIN sessions s ON r.session_id=s.id JOIN games g ON s.game_id=g.id LEFT JOIN bets b ON b.round_id=r.id LEFT JOIN players p ON p.id=b.player_id ORDER BY r.id DESC"),use_container_width=True)
    with tabs[5]:
        st.subheader("Shift control")
        if st.button("Open new cage shift",type="primary"):
            ref="SHIFT-"+uuid.uuid4().hex[:8].upper(); execsql("INSERT INTO cage_shifts(shift_ref,cashier,opening_float,opened_at) VALUES(?,?,?,?)",(ref,st.session_state.user['username'],0,now())); st.success(ref)
        st.dataframe(df("SELECT * FROM cage_shifts ORDER BY id DESC"),use_container_width=True)
    with tabs[6]:
        st.dataframe(df("SELECT event_type,count(*) events,round(sum(amount),2) net_value FROM ledger GROUP BY event_type ORDER BY event_type"),use_container_width=True)
        st.dataframe(df("SELECT method,direction,count(*) count,round(sum(amount),2) amount FROM settlement GROUP BY method,direction"),use_container_width=True)


def admin_portal():
    st.title("⚙️ Casino Management")
    c=st.columns(5); c[0].metric("Players",scalar("SELECT count(*) FROM players")); c[1].metric("Ledger Events",scalar("SELECT count(*) FROM ledger")); c[2].metric("Rounds",scalar("SELECT count(*) FROM rounds")); c[3].metric("Token Accounts",scalar("SELECT count(*) FROM token_accounts")); c[4].metric("Open Flags",scalar("SELECT count(*) FROM compliance_flags WHERE status='OPEN'"))
    tabs=st.tabs(["Dashboard","Players","Games","Token Parameters","Ledger","Audit","Compliance"])
    with tabs[0]:
        x=df("SELECT event_type,count(*) events,round(sum(amount),2) value FROM ledger GROUP BY event_type");
        if not x.empty: st.plotly_chart(px.bar(x,x='event_type',y='value',title='Ledger value by event type'),use_container_width=True)
    with tabs[1]: st.dataframe(df("SELECT * FROM players ORDER BY id DESC"),use_container_width=True)
    with tabs[2]: st.dataframe(df("SELECT * FROM games ORDER BY id"),use_container_width=True)
    with tabs[3]:
        st.subheader("Operational parameters")
        with st.form("params"):
            maxbuy=st.number_input("Maximum single purchase (₹)",min_value=100.0,value=float(scalar("SELECT value FROM casino_config WHERE key='max_single_purchase'")),step=1000.0)
            maxred=st.number_input("Maximum single redemption (₹)",min_value=100.0,value=float(scalar("SELECT value FROM casino_config WHERE key='max_single_redemption'")),step=1000.0)
            threshold=st.number_input("Maker-checker threshold (₹)",min_value=0.0,value=float(scalar("SELECT value FROM casino_config WHERE key='maker_checker_threshold'")),step=10000.0)
            requirekyc=st.checkbox("Require verified KYC before play/funding",value=scalar("SELECT value FROM casino_config WHERE key='require_kyc_for_play'")=='1')
            if st.form_submit_button("Save parameters"):
                for k,v in [('max_single_purchase',maxbuy),('max_single_redemption',maxred),('maker_checker_threshold',threshold),('require_kyc_for_play','1' if requirekyc else '0')]: execsql("INSERT OR REPLACE INTO casino_config(key,value) VALUES(?,?)",(k,str(v))); audit("ADMIN","CONFIG_UPDATE","casino_config","parameters",json.dumps(dict(max_single_purchase=maxbuy,max_single_redemption=maxred,maker_checker_threshold=threshold))) ; st.success("Parameters saved")
        st.dataframe(df("SELECT code,name,cashable,transferable,redeemable,active FROM token_types"),use_container_width=True)
    with tabs[4]:
        x=df("SELECT * FROM ledger ORDER BY id DESC"); st.dataframe(x,use_container_width=True,height=500); st.download_button("Export ledger",x.to_csv(index=False).encode(),"ledger.csv","text/csv")
    with tabs[5]: st.dataframe(df("SELECT * FROM audit ORDER BY id DESC"),use_container_width=True,height=500)
    with tabs[6]: st.dataframe(df("SELECT * FROM compliance_flags ORDER BY id DESC"),use_container_width=True)


def investigator_portal():
    st.title("🔎 Investigator & Tax Audit")
    st.caption("Only this role can configure and generate tax statements in the prototype.")
    tabs=st.tabs(["Risk Dashboard","Player Investigation","Reconstruction","Tax Configuration","Tax Statement","Tax Reconciliation","Hash Verification","Exports"])
    with tabs[0]:
        st.dataframe(df("""SELECT p.player_code,p.name,p.risk_level,p.kyc_status,p.account_status,
        COALESCE(SUM(CASE WHEN l.event_type IN ('WINNING','JACKPOT') THEN l.amount ELSE 0 END),0) winnings,
        COALESCE(SUM(CASE WHEN l.event_type='BET' THEN -l.amount ELSE 0 END),0) wagers,
        COALESCE(SUM(CASE WHEN l.event_type='TOKEN_REDEMPTION' THEN -l.amount ELSE 0 END),0) redemptions
        FROM players p LEFT JOIN ledger l ON p.id=l.player_id GROUP BY p.id ORDER BY winnings DESC"""),use_container_width=True)
    with tabs[1]:
        code=st.text_input("Player code","PLR-1001",key="investplayer"); p=one("SELECT * FROM players WHERE player_code=?",(code,))
        if p:
            st.json({k:p[k] for k in ['player_code','name','pan','mobile','kyc_status','risk_level','account_status']}); st.dataframe(df("SELECT ts,event_type,amount,token_type,balance_before,balance_after,g.name game,l.table_no,l.reference,l.description,l.event_id FROM ledger l LEFT JOIN games g ON g.id=l.game_id WHERE l.player_id=? ORDER BY l.id",(p['id'],)),use_container_width=True)
    with tabs[2]:
        q=st.text_input("Event / reference / player / round"); s=f"%{q}%"; st.dataframe(df("SELECT l.event_id,l.ts,p.player_code,p.name,l.event_type,l.amount,l.token_type,l.balance_before,l.balance_after,g.name game,l.table_no,l.reference,l.description,l.record_hash FROM ledger l JOIN players p ON p.id=l.player_id LEFT JOIN games g ON g.id=l.game_id WHERE l.event_id LIKE ? OR l.reference LIKE ? OR p.player_code LIKE ? OR l.round_id IN (SELECT id FROM rounds WHERE round_code LIKE ?) ORDER BY l.id DESC",(s,s,s,s)),use_container_width=True)
    with tabs[3]:
        st.subheader("Configurable taxable events")
        current=one("SELECT * FROM tax_rules WHERE active=1 ORDER BY id DESC LIMIT 1")
        all_events=['TOKEN_ISSUE','BET','BET_RETURN','WINNING','JACKPOT','TOKEN_REDEMPTION','VOID','REVERSAL','COMP','TIP','ADJUSTMENT','MARKER_SETTLEMENT']
        selected=json.loads(current['taxable_event_types']) if current else ['WINNING','JACKPOT']
        with st.form("taxconfig"):
            rulecode=st.text_input("Rule code",current['rule_code'] if current else 'CUSTOM-TAX-RULE')
            eff_from=st.date_input("Effective from",date.fromisoformat(current['effective_from']) if current else date.today())
            eff_to=st.date_input("Effective to",date.fromisoformat(current['effective_to']) if current else date(2099,12,31))
            rate=st.number_input("Tax/TDS rate (%)",min_value=0.0,max_value=100.0,value=float(current['rate']) if current else 0.0,step=0.1)
            threshold=st.number_input("Tax-free / threshold amount (₹)",min_value=0.0,value=float(current['threshold']) if current else 0.0,step=100.0)
            deduction=st.number_input("Deduction from configured gross base (₹)",min_value=0.0,value=float(current['deduction']) if current else 0.0,step=100.0)
            selected=st.multiselect("Events included in taxable base",all_events,default=[x for x in selected if x in all_events])
            desc=st.text_area("Rule description",current['description'] if current else '')
            if st.form_submit_button("Save tax rule",type='primary'):
                # deactivate previous active rule, then create versioned rule
                execsql("UPDATE tax_rules SET active=0 WHERE active=1")
                execsql("INSERT INTO tax_rules(rule_code,effective_from,effective_to,rate,threshold,deduction,taxable_event_types,description,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(rulecode,str(eff_from),str(eff_to),rate,threshold,deduction,json.dumps(selected),desc,1,now()))
                audit(st.session_state.user['username'],'TAX_RULE_UPDATE','tax_rule',rulecode,json.dumps({'events':selected,'rate':rate,'threshold':threshold,'deduction':deduction})); st.success("Tax rule saved and versioned.")
        st.dataframe(df("SELECT rule_code,effective_from,effective_to,rate,threshold,deduction,taxable_event_types,active FROM tax_rules ORDER BY id DESC"),use_container_width=True)
    with tabs[4]:
        code=st.text_input("Player code", "PLR-1001",key="taxplayer"); p=one("SELECT * FROM players WHERE player_code=?",(code,)); c1,c2=st.columns(2); start=c1.date_input("Period from",date(date.today().year,4,1),key='taxstart'); end=c2.date_input("Period to",date.today(),key='taxend')
        if p and st.button("Generate Investigator Tax Statement",type='primary'):
            rule=one("SELECT * FROM tax_rules WHERE active=1 AND date(effective_from)<=date(?) AND date(effective_to)>=date(?) ORDER BY id DESC LIMIT 1",(str(end),str(end)))
            if not rule: st.error("No active tax rule covers the selected period.")
            else:
                ev=json.loads(rule['taxable_event_types']); placeholders=','.join('?' for _ in ev)
                rows=fetch(f"SELECT event_id,ts,event_type,amount,reference FROM ledger WHERE player_id=? AND event_type IN ({placeholders}) AND date(ts)>=date(?) AND date(ts)<=date(?) ORDER BY id",(p['id'],*ev,str(start),str(end)))
                gross=sum(float(r['amount']) for r in rows); base=max(0,gross-float(rule['deduction'])); eligible=max(0,base-float(rule['threshold'])); tax=eligible*float(rule['rate'])/100; net=gross-tax
                ref='TAX-'+uuid.uuid4().hex[:12].upper(); execsql("INSERT INTO tax_statements(statement_ref,player_id,period_from,period_to,rule_code,gross_base,deduction,eligible_winnings,tax_amount,net_amount,generated_by,generated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(ref,p['id'],str(start),str(end),rule['rule_code'],gross,rule['deduction'],eligible,tax,net,st.session_state.user['username'],now())); audit(st.session_state.user['username'],'TAX_STATEMENT_GENERATED','tax_statement',ref,f'player={p["id"]};rule={rule["rule_code"]};gross={gross};tax={tax}')
                a,b,c,d=st.columns(4); a.metric('Configured gross base',f'₹{gross:,.2f}'); b.metric('Eligible base',f'₹{eligible:,.2f}'); c.metric('Tax',f'₹{tax:,.2f}'); d.metric('Net',f'₹{net:,.2f}'); st.success(f'Statement {ref} generated under {rule["rule_code"]}.'); st.dataframe(pd.DataFrame(rows),use_container_width=True)
    with tabs[5]:
        x=df("SELECT p.player_code,p.name,COALESCE(SUM(CASE WHEN l.event_type IN ('WINNING','JACKPOT') THEN l.amount ELSE 0 END),0) winnings,COALESCE((SELECT SUM(tax_amount) FROM tax_statements ts WHERE ts.player_id=p.id),0) tax_generated FROM players p LEFT JOIN ledger l ON p.id=l.player_id GROUP BY p.id"); st.dataframe(x,use_container_width=True)
    with tabs[6]:
        rows=fetch("SELECT * FROM ledger ORDER BY id"); prev=''; bad=[]
        for r in rows:
            raw=json.dumps([r['event_id'],r['ts'],r['player_id'],r['event_type'],r['amount'],r['balance_before'],r['balance_after'],r['game_id'],r['session_id'],r['round_id'],r['token_type'],r['counter'],r['table_no'],r['reference'],r['description'],r['actor'],r['previous_hash']],separators=(',',':')); calc=hashlib.sha256(raw.encode()).hexdigest()
            if calc!=r['record_hash'] or r['previous_hash']!=prev: bad.append(r['event_id'])
            prev=r['record_hash']
        st.metric('Verified ledger events',f'{len(rows)-len(bad)}/{len(rows)}'); st.success('Hash chain intact.') if not bad else st.error(f'{len(bad)} hash-chain exceptions detected.')
    with tabs[7]:
        for title,sql,name in [('Ledger','SELECT * FROM ledger ORDER BY id','ledger.csv'),('Tax Statements','SELECT * FROM tax_statements ORDER BY id','tax_statements.csv'),('Audit','SELECT * FROM audit ORDER BY id','audit.csv')]:
            x=df(sql); st.download_button(f'Download {title}',x.to_csv(index=False).encode(),name,'text/csv')


def main():
    init()
    if 'user' not in st.session_state: login(); return
    sidebar(); role=st.session_state.user['role']
    if role=='PLAYER': player_portal()
    elif role=='CAGE': cage_portal()
    elif role=='ADMIN': admin_portal()
    elif role=='INVESTIGATOR': investigator_portal()

if __name__=='__main__': main()
