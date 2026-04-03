import streamlit as st
import sqlite3
import pandas as pd
import datetime
import os
import time

DB_FILE = '/opt/pmpr-crm/data/pmpr_leads.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=20, check_same_thread=False)
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS developers (twitter_handle TEXT PRIMARY KEY, status TEXT DEFAULT 'NEW', last_contacted_at TIMESTAMP, last_message_sent TEXT, total_launches INTEGER DEFAULT 1, notes TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS tokens (token_address TEXT PRIMARY KEY, developer_handle TEXT, token_name TEXT, ticker TEXT, platform TEXT, scraped_at TIMESTAMP, current_mcap REAL DEFAULT 0, ath_mcap REAL DEFAULT 0, FOREIGN KEY (developer_handle) REFERENCES developers (twitter_handle))''')
    c.execute('''CREATE TABLE IF NOT EXISTS templates (id INTEGER PRIMARY KEY AUTOINCREMENT, template_name TEXT, template_body TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM templates")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO templates (template_name, template_body) VALUES ('The Track-Record Pitch', 'Hey man, saw you launched {launch_count} tokens recently, and {latest_token} hit an ATH of {ath_mcap}! Next time you launch, check out PMPR to automate your volume.')")
        c.execute("INSERT INTO templates (template_name, template_body) VALUES ('The Standard Pitch', 'Just saw {latest_token} go live. If you want to automate your buybacks, try PMPR bot.')")
    conn.commit()
    conn.close()

init_db()

st.set_page_config(page_title="PMPR CRM", layout="wide")
st.title("🎯 PMPR Outreach Command Center")

conn = get_db_connection()
df_devs = pd.read_sql_query("SELECT * FROM developers", conn)
df_tokens = pd.read_sql_query("SELECT * FROM tokens", conn)

if not df_tokens.empty:
    latest_launches = df_tokens.groupby('developer_handle')['scraped_at'].max().reset_index()
    latest_launches.rename(columns={'scraped_at': 'latest_launch_date'}, inplace=True)
    df_devs = pd.merge(df_devs, latest_launches, how='left', left_on='twitter_handle', right_on='developer_handle')
else:
    df_devs['latest_launch_date'] = None

st.sidebar.header("Filter & Sort")
status_filter = st.sidebar.selectbox("Status Filter", ['NEW', 'CONTACTED', 'IGNORED', 'ALL'])
sort_by = st.sidebar.selectbox("Sort By", ["Newest Launch", "Most Launches", "Name (A-Z)", "Recently Contacted"])

filtered_devs = df_devs[df_devs['status'] == status_filter] if status_filter != 'ALL' else df_devs

if not filtered_devs.empty:
    if sort_by == "Newest Launch":
        filtered_devs = filtered_devs.sort_values(by='latest_launch_date', ascending=False, na_position='last')
    elif sort_by == "Most Launches":
        filtered_devs = filtered_devs.sort_values(by='total_launches', ascending=False)
    elif sort_by == "Name (A-Z)":
        filtered_devs = filtered_devs.sort_values(by='twitter_handle', ascending=True)
    elif sort_by == "Recently Contacted":
        filtered_devs = filtered_devs.sort_values(by='last_contacted_at', ascending=False, na_position='last')

selected_handle = st.sidebar.selectbox("Select Developer", filtered_devs['twitter_handle'].tolist() if not filtered_devs.empty else ["No leads found"])

if selected_handle and selected_handle != "No leads found":
    dev_data = filtered_devs[filtered_devs['twitter_handle'] == selected_handle].iloc[0]
    dev_tokens = df_tokens[df_tokens['developer_handle'] == selected_handle]
    
    st.header(f"Contacting: @{dev_data['twitter_handle']}")
    st.link_button("👀 View X Profile", f"https://x.com/{dev_data['twitter_handle']}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Total Launches:** {dev_data['total_launches']}")
        st.write(f"**Status:** `{dev_data['status']}`")
    with col2:
        if dev_data['status'] == 'CONTACTED':
            st.write(f"**Last Contacted:** {dev_data['last_contacted_at']}")
            
    st.subheader("📝 Internal Notes")
    current_note = dev_data.get('notes', '')
    if pd.isna(current_note): current_note = ''
    
    new_note = st.text_area("Add followers count, replies, or details here:", value=current_note, height=100)
    if st.button("💾 Save Note"):
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE developers SET notes = ? WHERE twitter_handle = ?", (new_note, dev_data['twitter_handle']))
            conn.commit()
            st.success("Note saved successfully!")
            time.sleep(0.5)
            st.rerun()
        except sqlite3.OperationalError as e:
            st.error(f"Database busy. Try again in 2 seconds.")

    st.subheader("Launch History")
    if not dev_tokens.empty:
        display_df = dev_tokens.copy()
        display_df['ath_mcap'] = display_df['ath_mcap'].apply(lambda x: f"${x:,.0f}")
        
        terminal = st.radio("🔗 Select Trading Terminal:", ["Axiom", "Photon", "BullX", "Dexscreener"], horizontal=True)
        
        def build_trade_link(ca):
            if terminal == "Axiom": return f"https://axiom.trade/meme/{ca}?chain=sol"
            elif terminal == "Photon": return f"https://photon-sol.tinyastro.io/en/lp/{ca}"
            elif terminal == "BullX": return f"https://neo.bullx.io/terminal?chainId=1399811149&address={ca}"
            else: return f"https://dexscreener.com/solana/{ca}"
                
        display_df['Trade'] = display_df['token_address'].apply(build_trade_link)
        
        display_df = display_df.rename(columns={'token_name': 'Name', 'ticker': 'Ticker', 'token_address': 'Contract Address', 'platform': 'Chain', 'ath_mcap': 'ATH MC', 'scraped_at': 'Discovered At'})
        
        st.dataframe(
            display_df[['Name', 'Ticker', 'Contract Address', 'Trade', 'Chain', 'ATH MC', 'Discovered At']], 
            column_config={"Trade": st.column_config.LinkColumn("Action", display_text=f"📈 Open in {terminal}")},
            width='stretch', hide_index=True
        )
        
        latest_token_name = dev_tokens.iloc[-1]['token_name']
        highest_ath = f"${dev_tokens['ath_mcap'].max():,.0f}"
    else:
        st.write("No token data found yet.")
        latest_token_name = "Unknown"
        highest_ath = "$0"

    st.divider()
    
    # --- NEW: TEMPLATE MANAGER ---
    st.subheader("Message Composer")
    
    with st.expander("⚙️ Create New Predefined Message"):
        st.caption("You can use these variables in your message: `{launch_count}`, `{latest_token}`, `{ath_mcap}`")
        new_template_name = st.text_input("Template Name (e.g., 'The Aggressive Pitch')")
        new_template_body = st.text_area("Message Body (e.g., 'Yo, {latest_token} looks sick...')", height=100)
        
        if st.button("➕ Save New Template"):
            if new_template_name and new_template_body:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO templates (template_name, template_body) VALUES (?, ?)", (new_template_name, new_template_body))
                conn.commit()
                st.success(f"Template '{new_template_name}' saved!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Please fill out both the Name and the Body.")
    # -----------------------------

    df_templates = pd.read_sql_query("SELECT * FROM templates", conn)
    selected_template = st.selectbox("Choose a Pitch Template", df_templates['template_name'].tolist())
    raw_template = df_templates[df_templates['template_name'] == selected_template].iloc[0]['template_body']
    
    # Safely inject variables (in case the user forgets one in their custom template)
    try:
        personalized_template = raw_template.format(launch_count=dev_data['total_launches'], latest_token=latest_token_name, ath_mcap=highest_ath)
    except KeyError:
        # Fallback if they use a weird variable format
        personalized_template = raw_template
        
    final_message = st.text_area("Edit Message Before Sending:", value=personalized_template, height=150)
    
    if st.button("🚀 Log Contact & Prepare Message", type="primary"):
        cursor = conn.cursor()
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE developers SET status = 'CONTACTED', last_contacted_at = ?, last_message_sent = ? WHERE twitter_handle = ?", (current_time, final_message, dev_data['twitter_handle']))
        conn.commit()
        st.success("✅ Logged in database! Copy the message above and DM them on X.")

else:
    st.info("No leads available. Waiting for the scraper...")

conn.close()
