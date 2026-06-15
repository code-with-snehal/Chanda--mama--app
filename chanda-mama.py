import streamlit as st
import time
import pandas as pd
from datetime import datetime, date
from supabase import create_client, Client
import urllib.parse
import io

@st.cache_resource
def init_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase: Client = init_supabase()
st.set_page_config(page_title="Chanda Mama", page_icon="🌙", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = ""
if 'selected_group_key' not in st.session_state: st.session_state.selected_group_key = "Personal"
if 'show_profile' not in st.session_state: st.session_state.show_profile = False
if 'active_tab' not in st.session_state: st.session_state.active_tab = "Add Expense"
if 'view_group_key' not in st.session_state: st.session_state.view_group_key = "Personal"

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

def add_expense(exp_date, category, amount, note, username, group_name, paid_by, split_between):
    try:
        supabase.table('expenses').insert({"exp_date": str(exp_date), "category": category, "amount": float(amount), "note": note, "username": username, "group_name": group_name, "paid_by": paid_by, "split_between": split_between}).execute()
        return True
    except: return False

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
        return True
    except: return False

def update_expense(exp_id, exp_date, category, amount, note, paid_by, split_between):
    try:
        supabase.table('expenses').update({"exp_date": str(exp_date), "category": category, "amount": float(amount), "note": note, "paid_by": paid_by, "split_between": split_between}).eq('id', exp_id).execute()
        return True
    except: return False

def get_expenses(username, group_name="Personal"):
    try:
        if group_name == "Personal": result = supabase.table('expenses').select("*").eq('username', username).eq('group_name', 'Personal').order('exp_date', desc=True).execute()
        else: result = supabase.table('expenses').select("*").eq('group_name', group_name).order('exp_date', desc=True).execute()
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
        if not split_between or split_between is None: split_between = members
        share = amount / len(split_between)
        if paid_by in balances: balances[paid_by] += amount
        for member in split_between:
            if member in balances: balances[member] -= share
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
.footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        text-align: center;
        padding: 10px;
        font-family: 'Arial', sans-serif;
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 1px;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
        z-index: 999;
    }
.footer span {
        background: linear-gradient(45deg, #fff, #f0f0f0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
    </style>
    <div class="footer">
        Made by <span>Snehal Mahure</span> • from <span>Snehal Mahure</span> ✨
    </div>
    """, unsafe_allow_html=True)

if not st.session_state.logged_in:
    st.title("🌙 Chanda Mama - Login Karo")
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
    st.title(f"🌙 Chanda Mama - Welcome {st.session_state.username}")

    col1, col2, col3 = st.columns([1, 8, 2])
    with col1:
        if st.button("🏠", use_container_width=True, help="Home - Add Expense"):
            st.session_state.selected_group_key = "Personal"
            st.session_state.show_profile = False
            st.session_state.active_tab = "Add Expense"
            st.rerun()
    with col2: st.write("")
    with col3:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("👤", use_container_width=True, help="Profile"):
                st.session_state.show_profile = not st.session_state.show_profile
                st.rerun()
        with col_b:
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
                    st.success("Profile updated successfully!")
                    time.sleep(1)
                    st.session_state.show_profile = False
                    st.rerun()
                else: st.error("Update failed")
            if col2.form_submit_button("❌ Cancel", use_container_width=True):
                st.session_state.show_profile = False
                st.rerun()
        st.divider()

    tab_names = ["💸 Add Expense", "📊 My Expenses", "👥 Groups", "💰 Settle Up", "📈 Reports"]
    tab1, tab2, tab3, tab4, tab5 = st.tabs(tab_names)

    with tab1:
        st.session_state.active_tab = "Add Expense"
        st.subheader("Naya Kharcha Add Kar")
        groups_data = get_user_groups(st.session_state.username)
        group_names = ["Personal"] + [g['group_name'] for g in groups_data]
        if st.session_state.selected_group_key not in group_names:
            st.session_state.selected_group_key = "Personal"
        selected_group = st.selectbox("Group Select Karo", group_names, key="group_selector_widget", index=group_names.index(st.session_state.selected_group_key))
        st.session_state.selected_group_key = selected_group

        if selected_group!= "Personal":
            st.subheader(f"💸 {selected_group}")
            col1, col2, col3 = st.columns([2, 2, 6])
            with col1:
                if st.button("✏️ Edit Group", use_container_width=True, key=f"edit_{selected_group}"):
                    st.session_state['edit_group'] = selected_group
            with col2:
                if st.button("🗑️ Delete Group", use_container_width=True, key=f'del_{selected_group}'):
                    st.session_state['delete_group'] = selected_group

            if st.session_state.get('edit_group') == selected_group:
                group_info = next((g for g in groups_data if g['group_name'] == selected_group), None)
                with st.form("edit_group_form"):
                    new_name = st.text_input("Naya naam", value=selected_group)
                    st.write("**Members Manage Karo:**")
                    members_to_remove = st.multiselect("Remove Members", [m for m in group_info['members'] if m!= st.session_state.username])
                    new_members = st.text_input("Add New Members - Comma separated", placeholder="newuser1,newuser2")
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("✅ Save Changes"):
                        updated_members = [m for m in group_info['members'] if m not in members_to_remove]
                        if new_members: updated_members.extend([m.strip() for m in new_members.split(",") if m.strip()])
                        updated_members = list(set(updated_members))
                        supabase.table('groups').update({'group_name': new_name, 'members': updated_members}).eq('group_name', selected_group).execute()
                        supabase.table('expenses').update({'group_name': new_name}).eq('group_name', selected_group).execute()
                        del st.session_state['edit_group']
                        st.session_state.selected_group_key = new_name
                        st.success("Group updated!")
                        time.sleep(1)
                        st.rerun()
                    if c2.form_submit_button("❌ Cancel"):
                        del st.session_state['edit_group']
                        st.rerun()

            if st.session_state.get('delete_group') == selected_group:
                st.error(f"**Pakka?** `{selected_group}` aur saare expenses ud jayenge!")
                c1, c2 = st.columns(2)
                if c1.button("🔥 Haan Uda Do", type="primary", key="confirm_del"):
                    supabase.table('expenses').delete().eq('group_name', selected_group).execute()
                    supabase.table('groups').delete().eq('group_name', selected_group).execute()
                    del st.session_state['delete_group']
                    st.session_state.selected_group_key = "Personal"
                    st.success("Group delete ho gaya!")
                    time.sleep(1)
                    st.rerun()
                if c2.button("Rehne Do", key="cancel_del"):
                    del st.session_state['delete_group']
                    st.rerun()
            st.divider()

        if selected_group!= "Personal":
            group_info = next((g for g in groups_data if g['group_name'] == selected_group), None)
            if group_info: current_members = group_info['members']
            else: current_members = [st.session_state.username]
        else: current_members = [st.session_state.username]

        with st.form("expense_form", clear_on_submit=True):
            exp_date = st.date_input("Date", value=date.today())
            category = st.selectbox("Category", ["Food", "Travel", "Shopping", "Bills", "Entertainment", "Rent", "Groceries", "Other"])
            amount = st.number_input("Amount ₹", min_value=0.01, step=1.0)
            note = st.text_input("Note")
            paid_by = st.selectbox("Paid By", current_members)
            if selected_group!= "Personal":
                valid_defaults = [m for m in current_members if m in current_members]
                split_between = st.multiselect("Split Between", current_members, default=valid_defaults)
            else: split_between = [st.session_state.username]
            if st.form_submit_button("Add Expense", use_container_width=True):
                if amount > 0 and split_between:
                    if add_expense(exp_date, category, amount, note, st.session_state.username, selected_group, paid_by, split_between):
                        st.success("Expense added!"); st.rerun()
                else: st.error("Amount aur Split Between daal")

    with tab2:
        st.session_state.active_tab = "My Expenses"
        st.subheader("Kharcha History & Edit")
        groups_data = get_user_groups(st.session_state.username)
        group_names = ["Personal"] + [g['group_name'] for g in groups_data]

        # FIX: on_change add kiya group change ke liye
        def change_view_group():
            st.session_state.view_group_key = st.session_state.view_group_widget

        selected_group = st.selectbox(
            "Group ka Kharcha Dekho",
            group_names,
            key="view_group_widget",
            index=group_names.index(st.session_state.view_group_key) if st.session_state.view_group_key in group_names else 0,
            on_change=change_view_group
        )

        df = get_expenses(st.session_state.username, st.session_state.view_group_key)

        if not df.empty:
            df['exp_date'] = pd.to_datetime(df['exp_date']).dt.date
            col1, col2, col3 = st.columns(3)
            with col1: search_term = st.text_input("🔍 Search Note", placeholder="Hotel, Bus...")
            with col2: filter_cat = st.selectbox("Filter Category", ["All"] + list(df['category'].unique()))
            with col3:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Export CSV", csv, f"{st.session_state.view_group_key}_expenses.csv", "text/csv", use_container_width=True)
            if search_term: df = df[df['note'].str.contains(search_term, case=False, na=False)]
            if filter_cat!= "All": df = df[df['category'] == filter_cat]

            for i, row in df.iterrows():
                with st.expander(f"{row['exp_date']} | {row['category']} | ₹{row['amount']:.2f}"):
                    st.write(f"**Note:** {row['note']} | **Paid by:** {row.get('paid_by', 'N/A')} | **Split:** {', '.join(row.get('split_between', []))}")
                    col1, col2 = st.columns(2)
                    if col1.button("✏️ Edit", key=f"edit_{row['id']}", use_container_width=True):
                        st.session_state.edit_id = row['id']; st.session_state.edit_data = row.to_dict(); st.session_state.edit_group = st.session_state.view_group_key; st.rerun()
                    if col2.button("🗑️ Delete", key=f"del_{row['id']}", use_container_width=True):
                        if delete_expense(row['id']): st.success("Deleted!"); st.rerun()

            if 'edit_id' in st.session_state:
                st.divider(); st.subheader("Expense Edit Karo")
                edit_data = st.session_state.edit_data
                current_members = [st.session_state.username]
                if st.session_state.edit_group!= "Personal":
                    group_info = next((g for g in groups_data if g['group_name'] == st.session_state.edit_group), None)
                    if group_info: current_members = group_info['members']
                with st.form("edit_expense_form"):
                    exp_date = st.date_input("Date", value=pd.to_datetime(edit_data['exp_date']).date())
                    cats = ["Food", "Travel", "Shopping", "Bills", "Entertainment", "Rent", "Groceries", "Other", "Settlement"]
                    category = st.selectbox("Category", cats, index=cats.index(edit_data['category']) if edit_data['category'] in cats else 0)
                    amount = st.number_input("Amount ₹", value=float(edit_data['amount']))
                    note = st.text_input("Note", value=edit_data['note'])
                    paid_by_index = current_members.index(edit_data['paid_by']) if edit_data['paid_by'] in current_members else 0
                    paid_by = st.selectbox("Paid By", current_members, index=paid_by_index)
                    valid_split = [m for m in edit_data.get('split_between', []) if m in current_members]
                    split_between = st.multiselect("Split Between", current_members, default=valid_split)
                    col1, col2 = st.columns(2)
                    if col1.form_submit_button("Update Karo", use_container_width=True):
                        if update_expense(st.session_state.edit_id, exp_date, category, amount, note, paid_by, split_between):
                            del st.session_state.edit_id, st.session_state.edit_data, st.session_state.edit_group; st.success("Updated!"); st.rerun()
                    if col2.form_submit_button("Cancel", use_container_width=True):
                        del st.session_state.edit_id, st.session_state.edit_data, st.session_state.edit_group; st.rerun()

            st.divider()
            col1, col2 = st.columns(2)
            col1.metric("Total Kharcha", f"₹{df['amount'].sum():,.2f}")
            col2.metric("Total Entries", len(df))
        else:
            st.info(f"{st.session_state.view_group_key} mein abhi tak koi kharcha nahi")

    with tab3:
        st.session_state.active_tab = "Groups"
        st.subheader("Naya Group Bana")
        with st.form("group_form", clear_on_submit=True):
            g_name = st.text_input("Group Name", placeholder="Goa Trip 2026")
            g_members = st.text_area("Members - Username comma se separate kar", placeholder="rahul,priya")
            if st.form_submit_button("Create Group", use_container_width=True):
                members_list = list(set([st.session_state.username] + [m.strip() for m in g_members.split(",") if m.strip()]))
                if len(g_name) > 2:
                    if create_group(g_name, members_list, st.session_state.username):
                        st.success(f"Group '{g_name}' ban gaya!"); st.rerun()
                    else: st.error("Group nahi bana")
                else: st.error("Group name 3 letters se bada daalo")
        st.divider(); st.subheader("Tere Groups")
        my_groups = get_user_groups(st.session_state.username)
        if my_groups:
            for g in my_groups:
                st.write(f"**{g['group_name']}** - Members: {', '.join(g['members'])} | Created by: {g['created_by']}")
        else: st.info("Tu kisi group mein nahi hai")

    with tab4:
        st.session_state.active_tab = "Settle Up"
        st.subheader("Hisaab Kitab - Settle Up")
        groups_data = get_user_groups(st.session_state.username)
        group_names = [g['group_name'] for g in groups_data]
        if group_names:
            selected_group = st.selectbox("Group Select Karo", group_names, key="settle_group")
            group_info = next((g for g in groups_data if g['group_name'] == selected_group), None)
            df = get_expenses(st.session_state.username, selected_group)
            if group_info and not df.empty:
                settlements, balances = calculate_settle_up(df, group_info['members'])
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Group Kharcha", f"₹{df['amount'].sum():,.2f}")
                col2.metric("Total Entries", len(df))
                settlements_df = df[df['category'] == 'Settlement']
                col3.metric("Settled Amount", f"₹{settlements_df['amount'].sum():,.2f}" if not settlements_df.empty else "₹0")
                st.divider()
                if settlements:
                    st.write("**Kaun Kisko Kitna Dega:**")
                    for s in settlements:
                        col1, col2, col3 = st.columns([3, 2, 2])
                        with col1: st.success(f"{s['from']} → {s['to']}: ₹{s['amount']:.2f}")
                        with col2:
                            payee_upi = get_user_upi(s['to'])
                            if payee_upi and s['from'] == st.session_state.username:
                                upi_link = generate_upi_link(payee_upi, s['to'], s['amount'], f"ChandaMama-{selected_group}")
                                st.link_button("💳 Pay via UPI", upi_link, use_container_width=True)
                            elif s['from'] == st.session_state.username: st.warning("UPI nahi mila")
                        with col3:
                            if s['from'] == st.session_state.username:
                                if st.button("✅ Mark as Paid", key=f"paid_{s['from']}_{s['to']}_{s['amount']}", use_container_width=True):
                                    if add_settlement(selected_group, s['from'], s['to'], s['amount'], f"Settlement for {selected_group}"):
                                        st.success("Payment recorded!"); time.sleep(1); st.rerun()
                    st.divider()
                    st.write("**Current Balances:**")
                    for member, bal in balances.items():
                        if bal > 0.01: st.info(f"🟢 {member} ko milenge: ₹{bal:.2f}")
                        elif bal < -0.01: st.warning(f"🔴 {member} ko dena hai: ₹{-bal:.2f}")
                        else: st.success(f"⚪ {member}: Settled")
                    if not settlements_df.empty:
                        st.divider()
                        st.write("**Settlement History:**")
                        for _, row in settlements_df.iterrows():
                            st.caption(f"{row['exp_date']} - {row['paid_by']} paid {row['split_between'][0]}: ₹{row['amount']:.2f}")
                else: st.balloons(); st.info("🎉 Sab barabar hai")
            else: st.info("Is group mein abhi kharcha nahi hua")
        else: st.info("Pehle group bana")

    with tab5:
        st.session_state.active_tab = "Reports"
        st.subheader("📈 Monthly Reports & Analytics")
        groups_data = get_user_groups(st.session_state.username)
        group_names = ["All"] + ["Personal"] + [g['group_name'] for g in groups_data]
        selected_group_report = st.selectbox("Group Select Karo", group_names, key="report_group")
        if selected_group_report == "All":
            all_df = pd.DataFrame()
            for g in ["Personal"] + [g['group_name'] for g in groups_data]:
                df_temp = get_expenses(st.session_state.username, g)
                if not df_temp.empty: all_df = pd.concat([all_df, df_temp])
            df = all_df
        else:
            df = get_expenses(st.session_state.username, selected_group_report)
        if not df.empty:
            df['exp_date'] = pd.to_datetime(df['exp_date'])
            df['Month'] = df['exp_date'].dt.to_period('M').astype(str)
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Spent", f"₹{df['amount'].sum():,.2f}")
            col2.metric("Total Entries", len(df))
            col3.metric("Avg per Entry", f"₹{df['amount'].mean():,.2f}")
            col4.metric("Categories", len(df['category'].unique()))
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Category-wise Breakdown")
                cat_summary = df.groupby('category')['amount'].sum().reset_index()
                st.dataframe(cat_summary, use_container_width=True, hide_index=True)
                st.bar_chart(df.groupby('category')['amount'].sum())
            with col2:
                st.subheader("Monthly Trend")
                month_summary = df.groupby('Month')['amount'].sum().reset_index()
                st.dataframe(month_summary, use_container_width=True, hide_index=True)
                st.line_chart(df.groupby('Month')['amount'].sum())
            st.divider()
            st.subheader("Who Paid How Much")
            st.bar_chart(df.groupby('paid_by')['amount'].sum())
        else: st.info("Koi data nahi mila")

    add_footer()
