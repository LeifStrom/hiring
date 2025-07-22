import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import time
from datetime import datetime
import numpy as np
from typing import Optional, Tuple, List
import random
import os

# Page configuration
st.set_page_config(
    page_title="Tread Athletics Hiring Dashboard",
    page_icon="⚡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
CREDENTIALS_FILE = "credentials.json"
SHEET_NAME = "Tread Hiring"
DENIED_SHEET_NAME = "Denied Applicants"
HIRED_SHEET_NAME = "Hired Applicants"
SKILL_COLUMNS = [
    "Throwing Skill", "Strength Skill", "Data Skill", 
    "Aptitude", "Professionalism", "Culture Fit", "Trust"
]

# Initialize session state
if 'last_sync' not in st.session_state:
    st.session_state.last_sync = None
if 'worksheet' not in st.session_state:
    st.session_state.worksheet = None
if 'denied_worksheet' not in st.session_state:
    st.session_state.denied_worksheet = None
if 'hired_worksheet' not in st.session_state:
    st.session_state.hired_worksheet = None

def retry_api_call(func, max_retries=3, base_delay=1):
    """Retry API calls with exponential backoff for rate limit errors."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_str = str(e).lower()
            if "quota exceeded" in error_str or "429" in error_str or "rate limit" in error_str:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    st.warning(f"⏳ Rate limit hit. Retrying in {delay:.1f} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    st.error("❌ Google Sheets API rate limit exceeded. Please wait a moment and try again.")
                    return None
            else:
                raise e
    return None

@st.cache_resource
def authenticate_google_sheets():
    """Authenticate with Google Sheets API using credentials."""
    try:
        # Try to use Streamlit secrets first (for deployment)
        if "gcp_service_account" in st.secrets:
            credentials_info = st.secrets["gcp_service_account"]
            credentials = Credentials.from_service_account_info(
                credentials_info, scopes=SCOPES
            )
        else:
            # Fallback to local credentials file (for development)
            if not os.path.exists(CREDENTIALS_FILE):
                st.error(f"❌ Credentials file '{CREDENTIALS_FILE}' not found!")
                st.info("💡 Please add your Google Service Account credentials to continue.")
                st.stop()
            
            credentials = Credentials.from_service_account_file(
                CREDENTIALS_FILE, scopes=SCOPES
            )
        
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"❌ Authentication failed: {str(e)}")
        st.stop()

def get_spreadsheet_by_name(client, sheet_name: str):
    """Find and open the spreadsheet by name."""
    try:
        # First try to open by name directly
        try:
            spreadsheet = client.open(sheet_name)
            return spreadsheet
        except gspread.SpreadsheetNotFound:
            pass
        
        # If direct access fails, search through available spreadsheets
        spreadsheets = client.list_spreadsheet_files()
        for sheet in spreadsheets:
            if sheet['name'] == sheet_name:
                spreadsheet = client.open_by_key(sheet['id'])
                return spreadsheet
        
        st.error(f"❌ Spreadsheet '{sheet_name}' not found or not accessible.")
        st.info("💡 Make sure you have shared the Google Sheet with your service account email address.")
        st.stop()
    except Exception as e:
        st.error(f"❌ Error accessing spreadsheet: {str(e)}")
        st.info("💡 Check your Google Sheets API credentials and permissions.")
        st.stop()

def get_or_create_worksheet(spreadsheet, worksheet_name: str):
    """Get existing worksheet or create a new one with proper headers."""
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        return worksheet
    except gspread.WorksheetNotFound:
        # Create the worksheet with headers
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)
        headers = [
            "name", "date of application", "date of birth"
        ] + SKILL_COLUMNS + ["Applicant Score"]
        worksheet.append_row(headers)
        return worksheet

def load_applicants_data(worksheet) -> pd.DataFrame:
    """Load applicants data from Google Sheets with rate limiting."""
    def _get_data():
        return worksheet.get_all_records()
    
    try:
        data = retry_api_call(_get_data)
        if data is None:
            return pd.DataFrame()
            
        if not data:
            columns = ["name", "date of application", "date of birth"] + SKILL_COLUMNS + ["Applicant Score"]
            return pd.DataFrame(columns=columns)
        
        df = pd.DataFrame(data)
        
        # Convert date columns to datetime
        for col in ["date of application", "date of birth"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Convert skill columns to numeric
        for col in SKILL_COLUMNS + ["Applicant Score"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"❌ Error loading data: {str(e)}")
        return pd.DataFrame()

def calculate_applicant_score(row_data: dict) -> float:
    """Calculate the mean score of all skill ratings."""
    scores = []
    for skill in SKILL_COLUMNS:
        score = row_data.get(skill, 0)
        if score and not pd.isna(score):
            scores.append(float(score))
    
    return round(float(np.mean(scores)), 2) if scores else 0.0

def update_applicant_scores(worksheet, df: pd.DataFrame, row_index: int, scores: dict):
    """Update applicant scores in the Google Sheet."""
    try:
        # Calculate applicant score
        applicant_score = calculate_applicant_score(scores)
        
        # Update the worksheet (add 2 to row_index: 1 for 0-based indexing, 1 for header row)
        sheet_row = row_index + 2
        
        # Find column indices for skills
        headers = worksheet.row_values(1)
        updates = []
        
        for skill, score in scores.items():
            if skill in headers:
                col_index = headers.index(skill) + 1  # 1-based indexing
                updates.append({
                    'range': f'{chr(64 + col_index)}{sheet_row}',
                    'values': [[score]]
                })
        
        # Add applicant score
        if "Applicant Score" in headers:
            col_index = headers.index("Applicant Score") + 1
            updates.append({
                'range': f'{chr(64 + col_index)}{sheet_row}',
                'values': [[applicant_score]]
            })
        
        # Batch update with rate limiting
        if updates:
            def _batch_update():
                return worksheet.batch_update(updates)
            
            result = retry_api_call(_batch_update)
            if result is None:
                st.error("❌ Failed to update scores due to rate limits. Please try again.")
                return
        
        st.success(f"✅ Scores updated for {df.iloc[row_index]['name']}")
        
    except Exception as e:
        st.error(f"❌ Error updating scores: {str(e)}")

def move_applicant_to_denied(main_worksheet, denied_worksheet, df: pd.DataFrame, row_index: int):
    """Move an applicant from main sheet to denied sheet."""
    try:
        # Get the row data
        row_data = df.iloc[row_index].to_dict()
        
        # Convert the row to a list for appending
        headers = main_worksheet.row_values(1)
        row_values = []
        for header in headers:
            value = row_data.get(header, '')
            if pd.isna(value):
                value = ''
            row_values.append(str(value))
        
        # Add to denied sheet
        denied_worksheet.append_row(row_values)
        
        # Remove from main sheet (add 2 for 0-based indexing and header row)
        main_worksheet.delete_rows(row_index + 2)
        
        st.success(f"✅ {row_data['name']} moved to denied applicants")
        
    except Exception as e:
        st.error(f"❌ Error moving applicant: {str(e)}")

def move_applicant_to_hired(main_worksheet, hired_worksheet, df: pd.DataFrame, row_index: int):
    """Move an applicant from main sheet to hired sheet."""
    try:
        # Get the row data
        row_data = df.iloc[row_index].to_dict()
        
        # Convert the row to a list for appending
        headers = main_worksheet.row_values(1)
        row_values = []
        for header in headers:
            value = row_data.get(header, '')
            if pd.isna(value):
                value = ''
            row_values.append(str(value))
        
        # Add to hired sheet
        hired_worksheet.append_row(row_values)
        
        # Remove from main sheet (add 2 for 0-based indexing and header row)
        main_worksheet.delete_rows(row_index + 2)
        
        st.success(f"✅ {row_data['name']} moved to hired applicants")
        
    except Exception as e:
        st.error(f"❌ Error moving applicant: {str(e)}")

def reinstate_applicant(main_worksheet, denied_worksheet, df: pd.DataFrame, row_index: int):
    """Move an applicant from denied sheet back to main sheet."""
    try:
        # Get the row data
        row_data = df.iloc[row_index].to_dict()
        
        # Convert the row to a list for appending
        headers = denied_worksheet.row_values(1)
        row_values = []
        for header in headers:
            value = row_data.get(header, '')
            if pd.isna(value):
                value = ''
            row_values.append(str(value))
        
        # Add to main sheet
        main_worksheet.append_row(row_values)
        
        # Remove from denied sheet
        denied_worksheet.delete_rows(row_index + 2)
        
        st.success(f"✅ {row_data['name']} reinstated to active applicants")
        
    except Exception as e:
        st.error(f"❌ Error reinstating applicant: {str(e)}")

def display_top_applicants(df: pd.DataFrame):
    """Display top 5 applicants in the sidebar."""
    if not df.empty:
        # Check if Applicant Score column exists, if not create it
        if 'Applicant Score' not in df.columns:
            df['Applicant Score'] = 0.0
            # Calculate scores for existing rows
            for idx, row in df.iterrows():
                score = calculate_applicant_score(row.to_dict())
                df.at[idx, 'Applicant Score'] = score
        
        # Get top 5 applicants
        top_5 = df.nlargest(5, 'Applicant Score')
        
        st.sidebar.markdown("## 🏆 Top 5 Applicants")
        
        for i, (_, applicant) in enumerate(top_5.iterrows(), 1):
            score = applicant.get('Applicant Score', 0)
            name = applicant.get('name', 'Unknown')
            
            # Color coding based on score
            if score is not None and score >= 8:
                color = "🟢"
            elif score is not None and score >= 6:
                color = "🟡"
            else:
                color = "🔴"
            
            st.sidebar.markdown(f"{i}. {color} **{name}** - {score:.2f}")
    else:
        st.sidebar.markdown("## 🏆 Top 5 Applicants")
        st.sidebar.info("No applicants with scores yet.")

def display_applicants_table(df: pd.DataFrame, worksheet, denied_worksheet, hired_worksheet):
    """Display the main applicants table with rating functionality."""
    if df.empty:
        st.info("📝 No applicants found. Add some data to your Google Sheet to get started.")
        return
    
    # Check if Applicant Score column exists, if not create it
    if 'Applicant Score' not in df.columns:
        df['Applicant Score'] = 0.0
        # Calculate scores for existing rows
        for idx, row in df.iterrows():
            score = calculate_applicant_score(row.to_dict())
            df.at[idx, 'Applicant Score'] = score
    
    # Sort by Applicant Score (descending)
    df_sorted = df.sort_values(by='Applicant Score', ascending=False, na_position='last')
    
    st.subheader(f"📊 Current Applicants ({len(df_sorted)})")
    
    # Display table with interactive elements
    for idx, (_, applicant) in enumerate(df_sorted.iterrows()):
        original_idx = df.index[df['name'] == applicant['name']].tolist()[0]
        
        with st.expander(f"**{applicant['name']}** - Score: {applicant.get('Applicant Score', 0):.2f}"):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                # Basic info
                st.write(f"**Application Date:** {applicant.get('date of application', 'N/A')}")
                st.write(f"**Date of Birth:** {applicant.get('date of birth', 'N/A')}")
                
                # Skill ratings
                scores = {}
                
                # Check if any scores have been modified
                has_changes = False
                for skill in SKILL_COLUMNS:
                    current_score = applicant.get(skill, 0)
                    if pd.isna(current_score).any() if hasattr(current_score, '__iter__') else pd.isna(current_score) or current_score is None:
                        current_score = 0
                    
                    # Convert current_score to int for comparison
                    current_score_int = int(current_score) if current_score and current_score > 0 else 1
                    
                    slider_value = st.slider(
                        skill.replace(' Skill', ''),
                        min_value=1,
                        max_value=10,
                        value=current_score_int,
                        key=f"{applicant['name']}_{skill}_{idx}",
                        help=f"Current: {current_score_int if current_score and current_score > 0 else 'Not set'}"
                    )
                    scores[skill] = slider_value
                    
                    # Check if score has changed
                    if slider_value != current_score_int:
                        has_changes = True
                
                # Show unsaved changes indicator
                if has_changes:
                    st.warning("⚠️ **Unsaved changes** - Click 'Save Scores' to update Google Sheets")
            
            with col2:
                st.write("")  # Spacing
                st.write("")  # Spacing
                
                # Action buttons (vertical layout)
                # Make save button more prominent when there are changes
                button_type = "primary" if has_changes else "secondary"
                button_text = "💾 Save Scores" + (" *" if has_changes else "")
                
                if st.button(button_text, key=f"save_{applicant['name']}_{idx}", type=button_type):
                    update_applicant_scores(worksheet, df, original_idx, scores)
                    st.success("✅ Scores saved to Google Sheets!")
                    time.sleep(1)  # Brief pause to show success message
                    st.rerun()
                
                if st.button(f"❌ Deny", key=f"deny_{applicant['name']}_{idx}"):
                    move_applicant_to_denied(worksheet, denied_worksheet, df, original_idx)
                    st.rerun()
                
                if st.button(f"✅ Hire", key=f"hire_{applicant['name']}_{idx}"):
                    move_applicant_to_hired(worksheet, hired_worksheet, df, original_idx)
                    st.rerun()

def display_denied_applicants(df: pd.DataFrame, main_worksheet, denied_worksheet):
    """Display denied applicants with reinstate functionality."""
    if df.empty:
        st.info("👍 No denied applicants.")
        return
    
    # Check if Applicant Score column exists, if not create it
    if 'Applicant Score' not in df.columns:
        df['Applicant Score'] = 0.0
        # Calculate scores for existing rows
        for idx, row in df.iterrows():
            score = calculate_applicant_score(row.to_dict())
            df.at[idx, 'Applicant Score'] = score
    
    # Sort by Applicant Score (descending)
    df_sorted = df.sort_values(by='Applicant Score', ascending=False, na_position='last')
    
    st.subheader(f"❌ Denied Applicants ({len(df_sorted)})")
    
    # Display as a table with reinstate buttons
    for idx, (_, applicant) in enumerate(df_sorted.iterrows()):
        original_idx = df.index[df['name'] == applicant['name']].tolist()[0]
        
        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        
        with col1:
            st.write(f"**{applicant['name']}**")
        
        with col2:
            st.write(f"Score: {applicant.get('Applicant Score', 0):.2f}")
        
        with col3:
            st.write(f"{applicant.get('date of application', 'N/A')}")
        
        with col4:
            if st.button(f"↩️ Reinstate", key=f"reinstate_{applicant['name']}_{idx}"):
                reinstate_applicant(main_worksheet, denied_worksheet, df, original_idx)
                st.rerun()

def display_hired_applicants(df: pd.DataFrame, main_worksheet, hired_worksheet):
    """Display hired applicants with reinstate functionality."""
    if df.empty:
        st.info("🎉 No hired applicants yet.")
        return
    
    # Check if Applicant Score column exists, if not create it
    if 'Applicant Score' not in df.columns:
        df['Applicant Score'] = 0.0
        # Calculate scores for existing rows
        for idx, row in df.iterrows():
            score = calculate_applicant_score(row.to_dict())
            df.at[idx, 'Applicant Score'] = score
    
    # Sort by Applicant Score (descending)
    df_sorted = df.sort_values(by='Applicant Score', ascending=False, na_position='last')
    
    st.subheader(f"💪🏼 Hired Applicants ({len(df_sorted)})")
    
    # Display as a table with reinstate buttons
    for idx, (_, applicant) in enumerate(df_sorted.iterrows()):
        original_idx = df.index[df['name'] == applicant['name']].tolist()[0]
        
        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        
        with col1:
            st.write(f"**{applicant['name']}**")
        
        with col2:
            st.write(f"Score: {applicant.get('Applicant Score', 0):.2f}")
        
        with col3:
            st.write(f"{applicant.get('date of application', 'N/A')}")
        
        with col4:
            if st.button(f"↩️ Reinstate", key=f"reinstate_hired_{applicant['name']}_{idx}"):
                reinstate_applicant(main_worksheet, hired_worksheet, df, original_idx)
                st.rerun()

def main():
    """Main application function."""
    st.title("⚡️ Tread Athletics Hiring Dashboard")
    st.markdown("---")
    
    # Initialize Google Sheets connection
    with st.spinner("🔄 Connecting to Google Sheets..."):
        client = authenticate_google_sheets()
        spreadsheet = get_spreadsheet_by_name(client, SHEET_NAME)
        
        # Get or create worksheets
        main_worksheet = get_or_create_worksheet(spreadsheet, SHEET_NAME)
        denied_worksheet = get_or_create_worksheet(spreadsheet, DENIED_SHEET_NAME)
        hired_worksheet = get_or_create_worksheet(spreadsheet, HIRED_SHEET_NAME)
        
        st.session_state.worksheet = main_worksheet
        st.session_state.denied_worksheet = denied_worksheet
        st.session_state.hired_worksheet = hired_worksheet
    
    # Load data
    with st.spinner("📊 Loading applicant data..."):
        applicants_df = load_applicants_data(main_worksheet)
        denied_df = load_applicants_data(denied_worksheet)
        hired_df = load_applicants_data(hired_worksheet)
        st.session_state.last_sync = datetime.now()
    
    # Sidebar
    st.sidebar.title("📈 Dashboard")
    st.sidebar.markdown(f"**Last Sync:** {st.session_state.last_sync.strftime('%H:%M:%S')}")
    

    
    # Display top applicants
    display_top_applicants(applicants_df)
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Data"):
        st.cache_resource.clear()
        st.rerun()
    
    # Main content tabs
    tab1, tab2, tab3 = st.tabs(["📝 Active Applicants", "❌ Denied Applicants", "💪🏼 Hired Applicants"])
    
    with tab1:
        display_applicants_table(applicants_df, main_worksheet, denied_worksheet, hired_worksheet)
    
    with tab2:
        display_denied_applicants(denied_df, main_worksheet, denied_worksheet)
    
    with tab3:
        display_hired_applicants(hired_df, main_worksheet, hired_worksheet)
    
    # Footer
    st.markdown("---")
    st.markdown("*Tread Athletics Hiring Dashboard - Built with Streamlit*")

if __name__ == "__main__":
    main() 
