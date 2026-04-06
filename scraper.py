import sqlite3
import time
import requests
import schedule
import datetime
import os

DB_FILE = '/opt/pmpr-crm/data/pmpr_leads.db'

def get_db():
    return sqlite3.connect(DB_FILE, timeout=20, check_same_thread=False)

def ensure_chart_state_column():
    conn = get_db()
    try:
        conn.execute("ALTER TABLE tokens ADD COLUMN chart_state TEXT DEFAULT 'consolidating'")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()

ensure_chart_state_column()

def clean_handle(url):
    if not url: return None
    handle = url.split('/')[-1].split('?')[0].replace('@', '')
    if 'twitter.com' in handle or 'x.com' in handle:
        handle = handle.split('/')[-1]
    handle = handle.strip()
    
    # --- NEW: Blacklist fake Twitter system routes ---
    invalid_handles = ['search', 'home', 'explore', 'intent', 'share', 'tweet']
    if handle.lower() in invalid_handles: 
        return None
        
    if handle.isdigit(): return None
    return handle

def sniper_job():
    print(f"[{datetime.datetime.now()}] 🎯 Scanning for fresh Solana leads...")
    try:
        resp = requests.get("https://api.dexscreener.com/token-profiles/latest/v1", timeout=15)
        if resp.status_code != 200: return
        
        profiles = resp.json()
        conn = get_db()
        c = conn.cursor()
        
        for item in profiles:
            if item.get('chainId') != 'solana': continue
            
            links = item.get('links', [])
            twitter_url = next((l['url'] for l in links if 'twitter.com' in l['url'] or 'x.com' in l['url']), None)
            
            handle = clean_handle(twitter_url)
            if not handle or len(handle) < 3: continue
            
            ca = item.get('tokenAddress')
            
            try:
                pair_resp = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{ca}", timeout=10).json()
            except:
                pair_resp = {}
                
            actual_name = "Unknown"
            ticker = "UNK"
            current_mc = 0
            chart_state = "consolidating"
            
            if pair_resp and 'pairs' in pair_resp and pair_resp['pairs']:
                main_pair = pair_resp['pairs'][0]
                actual_name = main_pair.get('baseToken', {}).get('name', 'Unknown')
                ticker = main_pair.get('baseToken', {}).get('symbol', 'UNK')
                current_mc = main_pair.get('fdv', 0)
                if current_mc == 0:
                    current_mc = main_pair.get('marketCap', 0)
                
                h1_change = main_pair.get('priceChange', {}).get('h1', 0)
                if h1_change > 15: chart_state = "pushing"
                elif h1_change > 0: chart_state = "recovering"
                elif h1_change < -20: chart_state = "dipping hard"
                elif h1_change < 0: chart_state = "bleeding slightly"

            c.execute("INSERT OR IGNORE INTO developers (twitter_handle, status, total_launches) VALUES (?, 'NEW', 0)", (handle,))
            
            c.execute("SELECT 1 FROM tokens WHERE token_address = ?", (ca,))
            is_new_token = c.fetchone() is None
            
            if is_new_token:
                c.execute("UPDATE developers SET total_launches = total_launches + 1 WHERE twitter_handle = ?", (handle,))
            
            c.execute("""
                INSERT OR IGNORE INTO tokens (token_address, developer_handle, token_name, ticker, platform, scraped_at, current_mcap, ath_mcap, chart_state) 
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """, (ca, handle, actual_name, ticker, "Solana", current_mc, current_mc, chart_state))
            
            if actual_name != "Unknown":
                c.execute("""
                    UPDATE tokens 
                    SET token_name = ?, ticker = ?, current_mcap = ?, chart_state = ?
                    WHERE token_address = ?
                """, (actual_name, ticker, current_mc, chart_state, ca))
            else:
                c.execute("UPDATE tokens SET current_mcap = ?, chart_state = ? WHERE token_address = ?", (current_mc, chart_state, ca))
                
            if current_mc > 0:
                c.execute("UPDATE tokens SET ath_mcap = MAX(ath_mcap, ?) WHERE token_address = ?", (current_mc, ca))

        conn.commit()
        conn.close()
        print(f"✅ Scan complete.")
    except Exception as e:
        print(f"❌ Scraper Error: {e}")

sniper_job()
schedule.every(2).minutes.do(sniper_job)

while True:
    schedule.run_pending()
    time.sleep(1)
