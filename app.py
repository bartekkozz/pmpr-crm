import streamlit as st
import sqlite3
import pandas as pd
import datetime
import os
import time

# --- USER ACCOUNTS ---
AUTHORIZED_USERS = {
    "bartekkozz": "pmpr2026",
#    "admin": "admin",
#    "agent1": "sales123"
    "KB": "PmprCrm2026",
    "Coringo": "PMPR2026crm!",
    "dp": "CRM2026!"
}

# Define who gets Admin privileges
ADMIN_ROLES = ["bartekkozz", "admin"]

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
    
    crm_columns = {
        'email': 'TEXT DEFAULT ""',
        'phone': 'TEXT DEFAULT ""',
        'telegram': 'TEXT DEFAULT ""',
        'address': 'TEXT DEFAULT ""',
        'is_saved_lead': 'INTEGER DEFAULT 0',
        'view_log': 'TEXT DEFAULT ""',
        'modification_log': 'TEXT DEFAULT ""' # NEW: Tracks who edits the profile
    }
    for col, dtype in crm_columns.items():
        try:
            c.execute(f"ALTER TABLE developers ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError:
            pass
            
    try:
        c.execute("ALTER TABLE tokens ADD COLUMN chart_state TEXT DEFAULT 'consolidating'")
    except sqlite3.OperationalError:
        pass

    c.execute("SELECT COUNT(*) FROM templates")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO templates (template_name, template_body) VALUES ('The Track-Record Pitch', 'Saw {token_name} launched {launch_time}. Chart looks like it is {chart_state}, but the {wallet_pattern}. We built internal tooling for this exact pattern.')")
    conn.commit()
    conn.close()

st.set_page_config(page_title="PMPR CRM", layout="wide")

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
    st.session_state['username'] = ''
    
if 'last_viewed_lead' not in st.session_state:
    st.session_state['last_viewed_lead'] = None

if not st.session_state['authenticated']:
    st.title("🔒 PMPR Secure Login")
    with st.form("login_form"):
        st.write("Please log in to access the Command Center.")
        username = st.text_input("Username").strip()
        password = st.text_input("Password", type="password").strip()
        submit = st.form_submit_button("Log In")
        
        if submit:
            if username in AUTHORIZED_USERS and AUTHORIZED_USERS[username] == password:
                st.session_state['authenticated'] = True
                st.session_state['username'] = username
                st.success("Login successful!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ Invalid username or password.")
else:
    init_db()
    conn = get_db_connection()
    
    col_title, col_playbook = st.columns([2, 1])
    with col_title:
        st.title("🎯 PMPR Outreach Command Center")
    with col_playbook:
        with st.expander("💡 Playbook: How to Convert", expanded=False):
            st.markdown("**Step 1:** Send 1 msg only\n**Step 2:** Wait for reply\n**Step 3:** Mirror their level\n**Step 4:** THEN introduce PMPR naturally:\n- *'we built internal tooling for this'*")

    df_devs = pd.read_sql_query("SELECT * FROM developers", conn)
    df_tokens = pd.read_sql_query("SELECT * FROM tokens", conn)

    if not df_tokens.empty:
        latest_launches = df_tokens.groupby('developer_handle')['scraped_at'].max().reset_index()
        latest_launches.rename(columns={'scraped_at': 'latest_launch_date'}, inplace=True)
        df_devs = pd.merge(df_devs, latest_launches, how='left', left_on='twitter_handle', right_on='developer_handle')
    else:
        df_devs['latest_launch_date'] = None

    current_user = st.session_state['username']
    is_admin = current_user in ADMIN_ROLES
    
    st.sidebar.header("Agent Status")
    st.sidebar.write(f"👤 Logged in as: **{current_user}**")
    if is_admin:
        st.sidebar.caption("🛡️ Admin Privileges Active")
        
    if st.sidebar.button("🚪 Log Out"):
        st.session_state['authenticated'] = False
        st.session_state['username'] = ''
        st.session_state['last_viewed_lead'] = None
        st.rerun()
    st.sidebar.divider()

    tab_radar, tab_crm = st.tabs(["📡 Live Radar (Scraping)", "🗄️ Lead Database (CRM)"])

    # ==========================================
    # TAB 1: LIVE RADAR
    # ==========================================
    with tab_radar:
        st.subheader("Target Acquisition")
        col_f1, col_f2 = st.columns(2)
        with col_f1: status_filter = st.selectbox("Status Filter", ['NEW', 'CONTACTED', 'IGNORED', 'ALL'], key="rf1")
        with col_f2: sort_by = st.selectbox("Sort By", ["Newest Launch", "Most Launches", "Name (A-Z)"], key="rf2")

        filtered_radar = df_devs[df_devs['status'] == status_filter] if status_filter != 'ALL' else df_devs
        if not filtered_radar.empty:
            if sort_by == "Newest Launch": filtered_radar = filtered_radar.sort_values(by='latest_launch_date', ascending=False, na_position='last')
            elif sort_by == "Most Launches": filtered_radar = filtered_radar.sort_values(by='total_launches', ascending=False)
            elif sort_by == "Name (A-Z)": filtered_radar = filtered_radar.sort_values(by='twitter_handle', ascending=True)

        selected_radar = st.selectbox("Select Developer", filtered_radar['twitter_handle'].tolist() if not filtered_radar.empty else ["No leads found"], key="rsel")

        if selected_radar and selected_radar != "No leads found":
            dev_data = filtered_radar[filtered_radar['twitter_handle'] == selected_radar].iloc[0]
            dev_tokens = df_tokens[df_tokens['developer_handle'] == selected_radar]
            
            if dev_data['is_saved_lead'] == 1:
                st.header(f"Contacting: @{dev_data['twitter_handle']} 🌟 [SAVED LEAD]")
            else:
                st.header(f"Contacting: @{dev_data['twitter_handle']}")
                
            col_b1, col_b2 = st.columns([1, 4])
            with col_b1: st.link_button("👀 View X Profile", f"https://x.com/{dev_data['twitter_handle']}")
            with col_b2:
                if dev_data['is_saved_lead'] == 0:
                    if st.button("⭐ Promote to CRM Lead", type="primary"):
                        c = conn.cursor()
                        c.execute("UPDATE developers SET is_saved_lead = 1 WHERE twitter_handle = ?", (dev_data['twitter_handle'],))
                        conn.commit()
                        st.success("Promoted to Lead Database!")
                        time.sleep(1)
                        st.rerun()

            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Total Launches:** {dev_data['total_launches']}")
                st.write(f"**Status:** `{dev_data['status']}`")
            with col2:
                if dev_data['status'] == 'CONTACTED':
                    st.write(f"**Last Contacted:** {dev_data['last_contacted_at']}")
                    
            st.subheader("Launch History")
            if not dev_tokens.empty:
                display_df = dev_tokens.copy()
                display_df['ath_mcap'] = display_df['ath_mcap'].apply(lambda x: f"${x:,.0f}")
                terminal = st.radio("🔗 Select Terminal:", ["Axiom", "Photon", "BullX", "Dexscreener"], horizontal=True, key="term1")
                def build_trade_link(ca):
                    if terminal == "Axiom": return f"https://axiom.trade/meme/{ca}?chain=sol"
                    elif terminal == "Photon": return f"https://photon-sol.tinyastro.io/en/lp/{ca}"
                    elif terminal == "BullX": return f"https://neo.bullx.io/terminal?chainId=1399811149&address={ca}"
                    else: return f"https://dexscreener.com/solana/{ca}"
                display_df['Trade'] = display_df['token_address'].apply(build_trade_link)
                display_df = display_df.rename(columns={'token_name': 'Name', 'ticker': 'Ticker', 'token_address': 'Contract Address', 'platform': 'Chain', 'ath_mcap': 'ATH MC', 'scraped_at': 'Discovered At'})
                st.dataframe(display_df[['Name', 'Ticker', 'Contract Address', 'Trade', 'Chain', 'ATH MC', 'Discovered At']], column_config={"Trade": st.column_config.LinkColumn("Action", display_text=f"📈 Open in {terminal}")}, width='stretch', hide_index=True)
            else:
                st.write("No token data found yet.")

            st.divider()
            
            st.subheader("📝 Internal Notes Log")
            current_note = dev_data.get('notes', '')
            if pd.isna(current_note): current_note = ''
            if current_note: st.info(current_note)
            new_note = st.text_area("Add a new note:", height=100, key="note1")
            if st.button("💾 Save Note", key="btn_note1"):
                if new_note.strip():
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    appended_note = f"🕒 {timestamp} | 👤 {current_user}\n{new_note}\n\n{current_note}".strip()
                    c = conn.cursor()
                    c.execute("UPDATE developers SET notes = ? WHERE twitter_handle = ?", (appended_note, dev_data['twitter_handle']))
                    conn.commit()
                    st.success("Saved!")
                    time.sleep(0.5)
                    st.rerun()

    # ==========================================
    # TAB 2: LEAD DATABASE (CRM View)
    # ==========================================
    with tab_crm:
        st.subheader("🗄️ Master CRM Directory")
        
        with st.expander("➕ Add Manual Lead (TG / Discord / Direct Contact)", expanded=False):
            with st.form("add_manual_lead_form"):
                st.markdown("Use this to manually input leads you found outside the scraper.")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    new_handle = st.text_input("Primary Handle (Required)*", placeholder="e.g. @whale_tg_name")
                    m_tg = st.text_input("Telegram Username")
                with col_m2:
                    m_email = st.text_input("Email Address")
                    m_address = st.text_input("Wallet Address")
                    
                m_notes = st.text_area("Initial Notes / Context")
                
                if st.form_submit_button("🚀 Create Lead"):
                    if new_handle.strip():
                        try:
                            clean_handle = new_handle.strip().replace("https://x.com/", "").replace("https://twitter.com/", "")
                            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                            initial_note = f"🕒 {timestamp} | 👤 {current_user} | ➕ Lead Manually Created\n{m_notes}" if m_notes.strip() else ""
                            initial_mod = f"✏️ {timestamp} | Lead created by 👤 {current_user}\n"
                            
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO developers (twitter_handle, status, is_saved_lead, total_launches, telegram, email, address, notes, modification_log) 
                                VALUES (?, 'NEW', 1, 0, ?, ?, ?, ?, ?)
                            """, (clean_handle, m_tg, m_email, m_address, initial_note, initial_mod))
                            conn.commit()
                            st.success(f"Lead {clean_handle} officially added to CRM!")
                            time.sleep(1)
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("❌ A lead with this exact handle already exists.")
                    else:
                        st.error("Please provide a Primary Handle.")
        
        crm_leads = df_devs[df_devs['is_saved_lead'] == 1]
        
        if crm_leads.empty:
            st.info("No leads promoted yet.")
        else:
            selected_crm = st.selectbox("Select VIP Lead", crm_leads['twitter_handle'].tolist(), key="csel")
            crm_data = crm_leads[crm_leads['twitter_handle'] == selected_crm].iloc[0]
            
            # --- VIEW TRACKER LOGIC ---
            if selected_crm != st.session_state['last_viewed_lead']:
                timestamp_view = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                current_view_log = crm_data.get('view_log', '')
                if pd.isna(current_view_log): current_view_log = ''
                
                new_view_entry = f"👁️ {timestamp_view} | Viewed by 👤 {current_user}\n"
                updated_view_log = new_view_entry + current_view_log
                
                c = conn.cursor()
                c.execute("UPDATE developers SET view_log = ? WHERE twitter_handle = ?", (updated_view_log, selected_crm))
                conn.commit()
                
                st.session_state['last_viewed_lead'] = selected_crm
                crm_data['view_log'] = updated_view_log
            # ---------------------------
            
            st.header(f"🌟 {crm_data['twitter_handle']}")
            if not crm_data['twitter_handle'].startswith('@') and not crm_data['twitter_handle'].lower().startswith('tg_'):
                st.link_button("👀 View X Profile", f"https://x.com/{crm_data['twitter_handle']}", key="xbtn2")
            
            col_logs1, col_logs2 = st.columns(2)
            
            # --- SECURITY: Hide View Audit from Agents ---
            with col_logs1:
                if is_admin:
                    with st.expander("👁️ Profile View Audit (Admins Only)"):
                        v_log = crm_data.get('view_log', '')
                        if v_log: st.text(v_log)
                        else: st.write("No views recorded yet.")
                else:
                    st.empty() # Leaves the space blank for standard agents
            
            # --- MODIFICATION LOG (Visible to Everyone) ---
            with col_logs2:
                with st.expander("✏️ Modification History"):
                    m_log = crm_data.get('modification_log', '')
                    if m_log: st.text(m_log)
                    else: st.write("No modifications recorded yet.")
            
            st.divider()
            
            st.subheader("Contact Information")
            with st.form("crm_update_form"):
                c1, c2 = st.columns(2)
                with c1:
                    new_tg = st.text_input("Telegram Username", value=crm_data.get('telegram', ''))
                    new_email = st.text_input("Email Address", value=crm_data.get('email', ''))
                with c2:
                    new_phone = st.text_input("Phone Number", value=crm_data.get('phone', ''))
                    new_address = st.text_input("Wallet/Physical Address", value=crm_data.get('address', ''))
                
                submit_crm = st.form_submit_button("💾 Save Lead Details")
                if submit_crm:
                    # Log the modification
                    timestamp_mod = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    current_mod_log = crm_data.get('modification_log', '')
                    if pd.isna(current_mod_log): current_mod_log = ''
                    updated_mod_log = f"✏️ {timestamp_mod} | Details updated by 👤 {current_user}\n" + current_mod_log
                    
                    c = conn.cursor()
                    c.execute("""UPDATE developers SET telegram=?, email=?, phone=?, address=?, modification_log=? WHERE twitter_handle=?""", 
                              (new_tg, new_email, new_phone, new_address, updated_mod_log, crm_data['twitter_handle']))
                    conn.commit()
                    st.success("Lead details and Modification History updated!")
                    time.sleep(0.5)
                    st.rerun()
                    
            st.divider()
            
            st.subheader("📝 Internal Notes Log")
            current_note = crm_data.get('notes', '')
            if pd.isna(current_note): current_note = ''
            if current_note: st.info(current_note)
            new_note2 = st.text_area("Add a new note:", height=100, key="note2")
            if st.button("💾 Save Note", key="btn_note2"):
                if new_note2.strip():
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    appended_note = f"🕒 {timestamp} | 👤 {current_user}\n{new_note2}\n\n{current_note}".strip()
                    c = conn.cursor()
                    c.execute("UPDATE developers SET notes = ? WHERE twitter_handle = ?", (appended_note, crm_data['twitter_handle']))
                    conn.commit()
                    st.success("Saved!")
                    time.sleep(0.5)
                    st.rerun()

    conn.close()
