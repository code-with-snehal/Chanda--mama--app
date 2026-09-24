import streamlit as st
import time
import pandas as pd
from datetime import datetime, date
from supabase import create_client, Client
import urllib.parse
import io
from PIL import Image
import re
import google.generativeai as genai

@st.cache_resource
def init_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase: Client = init_supabase()

# --- NEW: Gemini Setup ---
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
    AI_ENABLED = True
except:
    AI_ENABLED = False

st.set_page_config(page_title="Chanda Mama Pro", page_icon="🌙", layout="wide",menu_items={'Get Help': None,'Report a bug': None,'About': None})

# Session state init
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = ""
if 'selected_group_key' not in st.session_state: st.session_state.selected_group_key = "Personal"
if 'show_profile' not in st.session_state: st.session_state.show_profile = False
if 'view_group_key' not in st.session_state: st.session_state.view_group_key = "Personal"
if 'tab_index' not in st.session_state: st.session_state.tab_index = 0
if 'dark_mode' not in st.session_state: st.session_state.dark_mode = False

if st.session_state.dark_mode:
    st.markdown("""
    <style>
 .stApp { background-color: #0e1117; color: #fafafa; }
 .stSelectbox,.stTextInput,.stNumberInput { background-color: #262730; }
    </style>
    """, unsafe_allow_html=True)

def register_user(username, password, upi_id):
    try:
        check = supabase.table('users').select("*").eq('username', username).execute()
        if check.data: return False, "Username already exists"
        supabase.table('users').insert({"username": username, "password": password, "upi_id": upi_id}).execute()
        return True, "Registered successfully"
    except Exception as e: return False, str(e)

def login_user(username, password):
    try:
        result = supabase.table('users').select("*").eq('username', username).eq('password', password).execute()
        return bool(result.data)
    except: return False

def get_user_upi(username):
    try:
        result = supabase.table('users').select("upi_id").eq('username', username).execute()
        if result.data: return result.data[0]['upi_id']
        return ""
    except: return ""

def update_user_profile(username, new_upi, new_pass=None):
    try:
        update_data = {"upi_id": new_upi}
        if new_pass: update_data["password"] = new_pass
        supabase.table('users').update(update_data).eq('username', username).execute()
        return True
    except: return False

def upload_receipt(file, username):
    try:
        file_ext = file.name.split('.')[-1]
        file_name = f"{username}_{int(time.time())}.{file_ext}"
        supabase.storage.from_('receipts').upload(file_name, file.getvalue())
        url = supabase.storage.from_('receipts').get_public_url(file_name)
        return url
    except: return None

def add_expense(exp_date, category, amount, note, username, group_name, paid_by, split_between, split_type="Equal", split_values=None, receipt_url=None):
    try:
        data = {
            "exp_date": str(exp_date),
            "category": category,
            "amount": float(amount),
            "note": note,
            "username": username,
            "group_name": group_name,
            "paid_by": paid_by,
            "split_between": split_between,
            "split_type": split_type,
            "split_values": split_values,
            "receipt_url": receipt_url
        }
        supabase.table('expenses').insert(data).execute()
        add_activity(group_name, f"{paid_by} ne ₹{amount} ka {category} expense add kiya")
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

def add_settlement(group_name, paid_by, paid_to, amount, note):
    try:
        supabase.table('expenses').insert({
            "exp_date": str(date.today()),
            "category": "Settlement",
            "amount": float(amount),
            "note": f"Paid to {paid_to}: {note}",
            "username": paid_by,
            "group_name": group_name,
            "paid_by": paid_by,
            "split_between": [paid_to]
        }).execute()
        add_activity(group_name, f"{paid_by} ne {paid_to} ko ₹{amount} settle kiya")
        return True
    except: return False

def add_activity(group_name, activity):
    try:
        supabase.table('activities').insert({
            "group_name": group_name,
            "activity": activity,
            "timestamp": str(datetime.now())
        }).execute()
    except: pass

def get_activities(group_name):
    try:
        result = supabase.table('activities').select("*").eq('group_name', group_name).order('timestamp', desc=True).limit(10).execute()
        return result.data
    except: return []

def update_expense(exp_id, exp_date, category, amount, note, paid_by, split_between):
    try:
        supabase.table('expenses').update({"exp_date": str(exp_date), "category": category, "amount": float(amount), "note": note, "paid_by": paid_by, "split_between": split_between}).eq('id', exp_id).execute()
        return True
    except: return False

def get_expenses(username, group_name="Personal"):
    try:
        if group_name == "Personal":
            result = supabase.table('expenses').select("*").eq('username', username).eq('group_name', 'Personal').order('exp_date', desc=True).execute()
        else:
            result = supabase.table('expenses').select("*").eq('group_name', group_name).order('exp_date', desc=True).execute()
        return pd.DataFrame(result.data)
    except: return pd.DataFrame()

def delete_expense(exp_id):
    try:
        supabase.table('expenses').delete().eq('id', exp_id).execute()
        return True
    except: return False

def create_group(group_name, members, created_by):
    try:
        supabase.table('groups').insert({"group_name": group_name, "members": members, "created_by": created_by}).execute()
        add_activity(group_name, f"{created_by} ne group banaya")
        return True
    except: return False

def get_user_groups(username):
    try:
        result = supabase.table('groups').select("*").contains('members', [username]).execute()
        return result.data
    except: return []

def calculate_settle_up(df, members):
    if df.empty or not members: return [], {}
    balances = {m: 0.0 for m in members}
    for _, row in df.iterrows():
        paid_by = row['paid_by']
        amount = float(row['amount'])
        split_between = row.get('split_between', members)
        split_type = row.get('split_type', 'Equal')
        split_values = row.get('split_values', None)
        if not split_between or split_between is None: split_between = members
        if paid_by in balances: balances[paid_by] += amount
        if split_type == 'Equal':
            share = amount / len(split_between)
            for member in split_between:
                if member in balances: balances[member] -= share
        elif split_type == 'Exact' and split_values:
            for member, val in zip(split_between, split_values):
                if member in balances: balances[member] -= float(val)
        elif split_type == 'Percentage' and split_values:
            for member, pct in zip(split_between, split_values):
                if member in balances: balances[member] -= amount * float(pct) / 100
    creditors = {k: round(v, 2) for k, v in balances.items() if v > 0.01}
    debtors = {k: round(-v, 2) for k, v in balances.items() if v < -0.01}
    settlements = []
    d_list, c_list = list(debtors.items()), list(creditors.items())
    i, j = 0, 0
    while i < len(d_list) and j < len(c_list):
        debtor, debt_amt = d_list[i]; creditor, cred_amt = c_list[j]
        pay_amt = min(debt_amt, cred_amt)
        settlements.append({"from": debtor, "to": creditor, "amount": round(pay_amt, 2)})
        d_list[i] = (debtor, debt_amt - pay_amt); c_list[j] = (creditor, cred_amt - pay_amt)
        if d_list[i][1] < 0.01: i += 1
        if c_list[j][1] < 0.01: j += 1
    return settlements, balances

def generate_upi_link(payee_upi, payee_name, amount, note):
    params = {"pa": payee_upi, "pn": payee_name, "am": str(amount), "tn": note, "cu": "INR"}
    return f"upi://pay?{urllib.parse.urlencode(params)}"

def add_footer():
    st.markdown("""
    <style>
   .footer { position: fixed; left: 0; bottom: 0; width: 100%; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; text-align: center; padding: 10px; font-size: 14px; font-weight: 600; z-index: 999; }
    </style>
    <div class="footer">Made by <span>Snehal Mahure</span> • Chanda Mama Pro ✨</div>
    """, unsafe_allow_html=True)

if not st.session_state.logged_in:
    st.title("🌙 Chanda Mama Pro - Login Karo")
    tab1, tab2 = st.tabs(["Login", "Register"])
    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login", use_container_width=True):
            if login_user(username, password):
                st.session_state.logged_in = True; st.session_state.username = username; st.rerun()
            else: st.error("Galat username ya password")
    with tab2:
        new_user = st.text_input("New Username", key="reg_user")
        new_pass = st.text_input("New Password", type="password", key="reg_pass")
        upi = st.text_input("UPI ID", key="reg_upi", placeholder="username@upi")
        if st.button("Register", use_container_width=True):
            success, msg = register_user(new_user, new_pass, upi)
            if success: st.success(msg + " - Ab login karo")
            else: st.error(msg)
    add_footer()
else:
    st.title(f"🌙 Chanda Mama Pro - Welcome {st.session_state.username}")
    col1, col2, col3 = st.columns([1, 7, 3])
    with col1:
        if st.button("🏠", use_container_width=True, help="Home"):
            st.session_state.selected_group_key = "Personal"
            st.session_state.view_group_key = "Personal"
            st.session_state.show_profile = False
            st.session_state.tab_index = 0
            st.rerun()
    with col2: st.write("")
    with col3:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("🌙" if not st.session_state.dark_mode else "☀️", use_container_width=True):
                st.session_state.dark_mode = not st.session_state.dark_mode
                st.rerun()
        with col_b:
            if st.button("👤", use_container_width=True, help="Profile"):
                st.session_state.show_profile = not st.session_state.show_profile
                st.rerun()
        with col_c:
            if st.button("Logout", use_container_width=True):
                for key in list(st.session_state.keys()): del st.session_state[key]
                st.rerun()

    if st.session_state.show_profile:
        st.divider()
        st.subheader("👤 Profile Settings")
        current_upi = get_user_upi(st.session_state.username)
        with st.form("profile_form"):
            st.info(f"Username: **{st.session_state.username}**")
            new_upi = st.text_input("UPI ID", value=current_upi, placeholder="username@upi")
            st.write("**Password Change - Optional**")
            new_pass = st.text_input("New Password", type="password", placeholder="Khali chhod do agar change nahi karna")
            col1, col2 = st.columns(2)
            if col1.form_submit_button("✅ Update Profile", use_container_width=True):
                if update_user_profile(st.session_state.username, new_upi, new_pass if new_pass else None):
                    st.success("Profile updated successfully!"); time.sleep(1); st.session_state.show_profile = False; st.rerun()
                else: st.error("Update failed")
            if col2.form_submit_button("❌ Cancel", use_container_width=True):
                st.session_state.show_profile = False; st.rerun()
        st.divider()

    tab_names = ["📊 Dashboard", "💸 Add Expense", "📝 My Expenses", "👥 Groups", "💰 Settle Up", "📈 Reports", "🤖 AI Agent"]
    selected_tab = st.radio("", tab_names, index=st.session_state.tab_index, horizontal=True, label_visibility="collapsed")
    st.session_state.tab_index = tab_names.index(selected_tab)

    if selected_tab == "📊 Dashboard":
        st.subheader("📊 Dashboard - Sab Ek Nazar Mein")
        all_df = pd.DataFrame()
        groups_data = get_user_groups(st.session_state.username)
        for g in ["Personal"] + [g['group_name'] for g in groups_data]:
            df_temp = get_expenses(st.session_state.username, g)
            if not df_temp.empty: all_df = pd.concat([all_df, df_temp])
        if not all_df.empty:
            all_df['exp_date'] = pd.to_datetime(all_df['exp_date'])
            all_df['Month'] = all_df['exp_date'].dt.to_period('M').astype(str)
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Spent", f"₹{all_df['amount'].sum():,.2f}")
            col2.metric("This Month", f"₹{all_df[all_df['Month']==str(date.today())[:7]]['amount'].sum():,.2f}")
            col3.metric("Total Groups", len(groups_data))
            col4.metric("Total Entries", len(all_df))
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Monthly Trend")
                monthly = all_df.groupby('Month')['amount'].sum()
                st.line_chart(monthly)
            with col2:
                st.subheader("Top 5 Categories")
                top_cat = all_df.groupby('category')['amount'].sum().nlargest(5)
                st.bar_chart(top_cat)
        else:
            st.info("Abhi tak koi expense nahi. Add Expense se shuru kar!")

    elif selected_tab == "💸 Add Expense":
        st.subheader("Naya Kharcha Add Kar")
        groups_data = get_user_groups(st.session_state.username)
        group_names = ["Personal"] + [g['group_name'] for g in groups_data]
        def change_add_group():
            st.session_state.selected_group_key = st.session_state.add_group_widget
        selected_group = st.selectbox("Group Select Karo", group_names, key="add_group_widget", index=group_names.index(st.session_state.selected_group_key) if st.session_state.selected_group_key in group_names else 0, on_change=change_add_group)
        if st.session_state.selected_group_key!= "Personal":
            current_members = [st.session_state.username]
            group_info = next((g for g in groups_data if g['group_name'] == st.session_state.selected_group_key), None)
            if group_info: current_members = group_info['members']
        else: current_members = [st.session_state.username]
        with st.form("expense_form", clear_on_submit=True):
            exp_date = st.date_input("Date", value=date.today())
            category = st.selectbox("Category", ["Food", "Travel", "Shopping", "Bills", "Entertainment", "Rent", "Groceries", "Other"])
            amount = st.number_input("Amount ₹", min_value=0.01, step=1.0)
            note = st.text_input("Note")
            receipt = st.file_uploader("Receipt Upload - Optional", type=['jpg', 'png', 'jpeg'])
            paid_by = st.selectbox("Paid By", current_members)
            if st.session_state.selected_group_key!= "Personal":
                split_type = st.radio("Split Type", ["Equal", "Exact", "Percentage"], horizontal=True)
                split_between = st.multiselect("Split Between", current_members, default=current_members)
                split_values = None
                if split_type == "Exact" and split_between:
                    split_values = []
                    for member in split_between:
                        val = st.number_input(f"{member}", min_value=0.0, key=f"exact_{member}")
                        split_values.append(val)
                elif split_type == "Percentage" and split_between:
                    split_values = []
                    for member in split_between:
                        val = st.number_input(f"{member} %", min_value=0.0, max_value=100.0, key=f"pct_{member}")
                        split_values.append(val)
            else:
                split_between = [st.session_state.username]; split_type = "Equal"; split_values = None
            if st.form_submit_button("Add Expense", use_container_width=True):
                if amount > 0 and split_between:
                    receipt_url = upload_receipt(receipt, st.session_state.username) if receipt else None
                    if add_expense(exp_date, category, amount, note, st.session_state.username, st.session_state.selected_group_key, paid_by, split_between, split_type, split_values, receipt_url):
                        st.success("Expense added!"); st.rerun()

    elif selected_tab == "📝 My Expenses":
        st.subheader("Kharcha History")
        groups_data = get_user_groups(st.session_state.username)
        group_names = ["Personal"] + [g['group_name'] for g in groups_data]
        def change_view_group():
            st.session_state.view_group_key = st.session_state.view_group_widget
        st.selectbox("Group ka Kharcha Dekho", group_names, key="view_group_widget", index=group_names.index(st.session_state.view_group_key) if st.session_state.view_group_key in group_names else 0, on_change=change_view_group)
        df = get_expenses(st.session_state.username, st.session_state.view_group_key)
        if not df.empty:
            for i, row in df.iterrows():
                with st.expander(f"{row['exp_date']} | {row['category']} | ₹{row['amount']:.2f}"):
                    st.write(f"**Note:** {row['note']} | **Paid by:** {row.get('paid_by', 'N/A')}")
                    if st.button("🗑️ Delete", key=f"del_{row['id']}"):
                        if delete_expense(row['id']): st.success("Deleted!"); st.rerun()
        else: st.info("No data")

    elif selected_tab == "👥 Groups":
        st.subheader("Naya Group Bana")
        with st.form("group_form", clear_on_submit=True):
            g_name = st.text_input("Group Name")
            g_members = st.text_area("Members - comma se separate")
            if st.form_submit_button("Create Group", use_container_width=True):
                members_list = list(set([st.session_state.username] + [m.strip() for m in g_members.split(",") if m.strip()]))
                if create_group(g_name, members_list, st.session_state.username):
                    st.success(f"Group '{g_name}' ban gaya!"); st.rerun()

    elif selected_tab == "💰 Settle Up":
        st.subheader("Hisaab Kitab")
        groups_data = get_user_groups(st.session_state.username)
        group_names = [g['group_name'] for g in groups_data]
        if group_names:
            selected_group = st.selectbox("Group Select Karo", group_names, key="settle_group")
            group_info = next((g for g in groups_data if g['group_name'] == selected_group), None)
            df = get_expenses(st.session_state.username, selected_group)
            if group_info and not df.empty:
                settlements, balances = calculate_settle_up(df, group_info['members'])
                for s in settlements:
                    st.success(f"{s['from']} → {s['to']}: ₹{s['amount']:.2f}")

    elif selected_tab == "📈 Reports":
        st.subheader("📈 Reports")
        groups_data = get_user_groups(st.session_state.username)
        all_df = pd.DataFrame()
        for g in ["Personal"] + [g['group_name'] for g in groups_data]:
            df_temp = get_expenses(st.session_state.username, g)
            if not df_temp.empty: all_df = pd.concat([all_df, df_temp])
        if not all_df.empty:
            st.bar_chart(all_df.groupby('category')['amount'].sum())
            st.line_chart(all_df.groupby(pd.to_datetime(all_df['exp_date']).dt.to_period('M').astype(str))['amount'].sum())
        else: st.info("Koi data nahi")

    # --- NEW AI TAB ---
    elif selected_tab == "🤖 AI Agent":
        st.subheader("🤖 Chanda Mama AI - Tera 3-in-1 Assistant")
        if not AI_ENABLED:
            st.error("GEMINI_API_KEY nahi mila! Secrets me check kar.")
        else:
            st.markdown("**Bol ke likh:** `Kal raat 500 ka petrol dala` | **Puch:** `Is mahine sabse jyada kharcha kaha hua?` | **Samjha:** `Budget ka tip de`")
            user_q = st.text_area("Yaha likh...", height=120, placeholder="Ex: Goa trip me 2000 kharcha hua food pe")
            if st.button("🚀 AI Se Puch / Add Kar", type="primary"):
                if not user_q:
                    st.warning("Kuch to likh bhai!")
                else:
                    with st.spinner("Chanda Mama soch raha hai..."):
                        res = supabase.table('expenses').select("*").eq('username', st.session_state.username).order('id', desc=True).limit(15).execute()
                        context = str(res.data) if res.data else "No expenses yet"
                        prompt = f"""
                        Tu Chanda Mama hai, Pune ka ekdum desi, funny, Hinglish me baat karne wala finance dost.
                        User: {st.session_state.username}
                        Uske last 15 kharche: {context}
                        User ne bola: "{user_q}"

                        Tere 3 kaam hai:
                        1. Agar user ne koi NAYA KHARCHA bataya hai (jaise '500 petrol'), to tu is format me de: [EXPENSE] amount=500, category=Petrol, note=user message [/EXPENSE] - Category inme se chun: Food, Travel, Shopping, Bills, Entertainment, Rent, Groceries, Other, Petrol
                        2. Agar user ne koi SAWAAL pucha (report, analysis), to uske data se jawab de. Thoda daant, thoda pyaar se.
                        3. Agar TIP manga, to 2-3 practical tip de Pune ke hisab se.

                        Jawab hamesha Hinglish, chota, funny aur helpful.
                        """
                        try:
                            response = ai_model.generate_content(prompt)
                            ans = response.text
                            st.markdown("#### 🗣️ Chanda Mama Bola:")
                            st.markdown(ans)

                            # Auto Add Logic
                            if "[EXPENSE]" in ans:
                                m_amt = re.search(r'amount=(\d+)', ans)
                                m_cat = re.search(r'category=([A-Za-z]+)', ans)
                                m_note = re.search(r'note=(.*?)\s*\[/EXPENSE\]', ans, re.DOTALL)
                                if m_amt:
                                    amt = int(m_amt.group(1))
                                    cat = m_cat.group(1) if m_cat else "Other"
                                    note_text = m_note.group(1).strip() if m_note else user_q
                                    st.divider()
                                    st.info(f"AI ne pakda 👉 ₹{amt} - {cat} - '{note_text}'")
                                    if st.button(f"✅ Haan, ₹{amt} Add Kar De Personal me", use_container_width=True):
                                        if add_expense(date.today(), cat, amt, note_text, st.session_state.username, "Personal", st.session_state.username, [st.session_state.username]):
                                            st.success(f"Ho gaya! ₹{amt} add ho gaya AI se!")
                                            st.balloons()
                        except Exception as e:
                            st.error(f"AI Error: {e}")

    add_footer()
