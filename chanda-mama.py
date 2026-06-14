import streamlit as st
import time
import pandas as pd
from datetime import datetime, date
from supabase import create_client, Client

@st.cache_resource
def init_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase: Client = init_supabase()
st.set_page_config(page_title="Chanda Mama", page_icon="🌙", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = ""

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

def add_expense(exp_date, category, amount, note, username, group_name, paid_by, split_between):
    try:
        supabase.table('expenses').insert({"exp_date": str(exp_date), "category": category, "amount": float(amount), "note": note, "username": username, "group_name": group_name, "paid_by": paid_by, "split_between": split_between}).execute()
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
    if df.empty or not members: return []
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
        settlements.append(f"{debtor} → {creditor}: ₹{pay_amt:.2f}")
        d_list[i] = (debtor, debt_amt - pay_amt); c_list[j] = (creditor, cred_amt - pay_amt)
        if d_list[i][1] < 0.01: i += 1
        if c_list[j][1] < 0.01: j += 1
    return settlements

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
        upi = st.text_input("UPI ID", key="reg_upi")
        if st.button("Register", use_container_width=True):
            success, msg = register_user(new_user, new_pass, upi)
            if success: st.success(msg + " - Ab login karo")
            else: st.error(msg)
else:
    st.title(f"🌙 Chanda Mama - Welcome {st.session_state.username}")
    if st.sidebar.button("Logout"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["💸 Add Expense", "📊 My Expenses", "👥 Groups", "💰 Settle Up"])

    with tab1:
        st.subheader("Naya Kharcha Add Kar")
        groups_data = get_user_groups(st.session_state.username)
        group_names = ["Personal"] + [g['group_name'] for g in groups_data]
        selected_group = st.selectbox("Group Select Karo", group_names)

        if selected_group!= "Personal":
            col1, col2, col3, col4 = st.columns([1, 6, 1, 1])

            with col1:
                if st.button("🔙", use_container_width=True, key=f"back_{selected_group}"):
                    st.rerun()

            with col2:
                st.subheader(f"💸 {selected_group}")

            with col3:
                if st.button("✏️", use_container_width=True, key=f"edit_{selected_group}"):
                    st.session_state['edit_group'] = selected_group

            with col4:
                if st.button("🗑️", use_container_width=True, key=f'del_{selected_group}'):
                    st.session_state['delete_group'] = selected_group

            if st.session_state.get('edit_group') == selected_group:
                with st.form("edit_group_form"):
                    new_name = st.text_input("Naya naam", value=selected_group)
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("✅ Save"):
                        supabase.table('groups').update({'group_name': new_name}).eq('group_name', selected_group).eq('created_by', st.session_state.username).execute()
                        supabase.table('expenses').update({'group_name': new_name}).eq('group_name', selected_group).execute()
                        del st.session_state['edit_group']
                        st.success("Naam badal gaya!")
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
                    supabase.table('groups').delete().eq('group_name', selected_group).eq('created_by', st.session_state.username).execute()
                    del st.session_state['delete_group']
                    st.success("Group delete ho gaya!")
                    time.sleep(1)
                    st.rerun()
                if c2.button("Rehne Do", key="cancel_del"):
                    del st.session_state['delete_group']
                    st.rerun()

            st.divider()

        if selected_group!= "Personal":
            group_info = next((g for g in groups_data if g['group_name'] == selected_group), None)
            if group_info:
                current_members = group_info['members']
            else:
                current_members = [st.session_state.username]
        else:
            current_members = [st.session_state.username]

        with st.form("expense_form", clear_on_submit=True):
            exp_date = st.date_input("Date", value=date.today())
            category = st.selectbox("Category", ["Food", "Travel", "Shopping", "Bills", "Entertainment", "Rent", "Groceries", "Other"])
            amount = st.number_input("Amount ₹", min_value=0.01, step=1.0)
            note = st.text_input("Note")
            paid_by = st.selectbox("Paid By", current_members)

            if selected_group!= "Personal":
                split_between = st.multiselect("Split Between", current_members, default=current_members)
            else:
                split_between = [st.session_state.username]

            if st.form_submit_button("Add Expense", use_container_width=True):
                if amount > 0 and split_between:
                    if add_expense(exp_date, category, amount, note, st.session_state.username, selected_group, paid_by, split_between):
                        st.success("Expense added!"); st.rerun()
                else: st.error("Amount aur Split Between daal")

    with tab2:
        st.subheader("Kharcha History & Edit")
        groups_data = get_user_groups(st.session_state.username)
        group_names = ["Personal"] + [g['group_name'] for g in groups_data]
        selected_group = st.selectbox("Group ka Kharcha Dekho", group_names, key="view_group")
        df = get_expenses(st.session_state.username, selected_group)
        if not df.empty:
            df['exp_date'] = pd.to_datetime(df['exp_date']).dt.date
            for i, row in df.iterrows():
                with st.expander(f"{row['exp_date']} | {row['category']} | ₹{row['amount']:.2f}"):
                    st.write(f"**Note:** {row['note']} | **Paid by:** {row.get('paid_by', 'N/A')} | **Split:** {', '.join(row.get('split_between', []))}")
                    col1, col2 = st.columns(2)
                    if col1.button("✏️ Edit", key=f"edit_{row['id']}", use_container_width=True):
                        st.session_state.edit_id = row['id']; st.session_state.edit_data = row.to_dict(); st.session_state.edit_group = selected_group; st.rerun()
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
                    cats = ["Food", "Travel", "Shopping", "Bills", "Entertainment", "Rent", "Groceries", "Other"]
                    category = st.selectbox("Category", cats, index=cats.index(edit_data['category']) if edit_data['category'] in cats else 0)
                    amount = st.number_input("Amount ₹", value=float(edit_data['amount']))
                    note = st.text_input("Note", value=edit_data['note'])
                    paid_by = st.selectbox("Paid By", current_members, index=current_members.index(edit_data['paid_by']) if edit_data['paid_by'] in current_members else 0)
                    split_between = st.multiselect("Split Between", current_members, default=edit_data['split_between'])
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
            st.divider(); st.subheader("Category-wise Graph")
            st.bar_chart(df.groupby('category')['amount'].sum())
        else: st.info("Abhi tak koi kharcha nahi")

    with tab3:
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
            for g in my_groups: st.write(f"**{g['group_name']}** - Members: {', '.join(g['members'])}")
        else: st.info("Tu kisi group mein nahi hai")

    with tab4:
        st.subheader("Hisaab Kitab - Settle Up")
        groups_data = get_user_groups(st.session_state.username)
        group_names = [g['group_name'] for g in groups_data]
        if group_names:
            selected_group = st.selectbox("Group Select Karo", group_names, key="settle_group")
            group_info = next((g for g in groups_data if g['group_name'] == selected_group), None)
            df = get_expenses(st.session_state.username, selected_group)
            if group_info and not df.empty:
                settlements = calculate_settle_up(df, group_info['members'])
                col1, col2 = st.columns(2)
                col1.metric("Total Group Kharcha", f"₹{df['amount'].sum():,.2f}")
                col2.metric("Total Entries", len(df))
                st.divider()
                if settlements:
                    st.write("**Kaun Kisko Kitna Dega:**")
                    for s in settlements: st.success(s)
                else: st.balloons(); st.info("🎉 Sab barabar hai")
            else: st.info("Is group mein abhi kharcha nahi hua")
        else: st.info("Pehle group bana")
