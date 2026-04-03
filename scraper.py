import sqlite3
import time
import requests
import schedule
import datetime
import os

DB_FILE = '/opt/pmpr-crm/data/pmpr_leads.db'

def get_db():
    return sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)

def clean_handle(url):
    if not url: return None
    handle = url.split('/')[-1].split('?')[0].replace('@', '')
    if 'twitter.com' in handle or 'x.com' in handle:
        handle = handle.split('/')[-1]
    handle = handle.strip()
    
    # 🛑 THE FILTER: Completely ignore raw numbers/ghost accounts
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
            
            # Fetch Real Name, Ticker, and MC
            try:
                pair_resp = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{ca}", timeout=10).json()
            except:
                pair_resp = {}
                
            actual_name = "Unknown"
            ticker = "UNK"
            current_mc = 0
            
            if pair_resp and 'pairs' in pair_resp and pair_resp['pairs']:
                main_pair = pair_resp['pairs'][0]
                actual_name = main_pair.get('baseToken', {}).get('name', 'Unknown')
                ticker = main_pair.get('baseToken', {}).get('symbol', 'UNK')
                current_mc = main_pair.get('fdv', 0)
                if current_mc == 0:
                    current_mc = main_pair.get('marketCap', 0)

            # Update Developers
            c.execute("INSERT OR IGNORE INTO developers (twitter_handle, status, total_launches) VALUES (?, 'NEW', 0)", (handle,))
            c.execute("UPDATE developers SET total_launches = total_launches + 1 WHERE twitter_handle = ?", (handle,))
            
            # Insert Token (Now with Ticker & CA)
            c.execute("""
                INSERT OR IGNORE INTO tokens (token_address, developer_handle, token_name, ticker, platform, scraped_at, current_mcap, ath_mcap) 
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            """, (ca, handle, actual_name, ticker, "Solana", current_mc, current_mc))
            
            # Update existing MC
            c.execute("UPDATE tokens SET current_mcap = ? WHERE token_address = ?", (current_mc, ca))
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
