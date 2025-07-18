# Tread Athletics Hiring Dashboard

A comprehensive Streamlit application for managing and rating job applicants with Google Sheets integration.

## Features

- **Google Sheets Integration**: Automatically syncs with your "Tread Hiring" Google Sheet
- **Dual Worksheet Support**: Manages both active applicants and denied applicants
- **Interactive Rating System**: 1-10 sliders for seven key skills
- **Automatic Scoring**: Calculates and displays applicant scores
- **Top Performers**: Shows top 5 applicants in the sidebar
- **Move Functionality**: Deny applicants or reinstate them
- **Real-time Updates**: Changes are immediately reflected in Google Sheets

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Google Sheets Setup

1. Create a Google Cloud Project and enable the Google Sheets API
2. Create a service account and download the credentials JSON file
3. Rename the credentials file to `credentials.json` and place it in the project root
4. Share your "Tread Hiring" Google Sheet with the service account email

### 3. Google Sheet Structure

Your Google Sheet should have the following columns:
- **name**: Full name of the applicant
- **date of application**: YYYY-MM-DD format
- **date of birth**: YYYY-MM-DD format
- **Throwing Skill**: Rating 1-10
- **Strength Skill**: Rating 1-10
- **Data Skill**: Rating 1-10
- **Aptitude**: Rating 1-10
- **Professionalism**: Rating 1-10
- **Culture Fit**: Rating 1-10
- **Trust**: Rating 1-10
- **Applicant Score**: Automatically calculated average

### 4. Run the Application

```bash
streamlit run app.py
```

## Usage

1. **Active Applicants Tab**: 
   - View all current applicants
   - Rate applicants using the 1-10 sliders
   - Save scores to update Google Sheets
   - Deny applicants to move them to the denied list

2. **Denied Applicants Tab**:
   - View previously denied applicants
   - Reinstate applicants back to the active list

3. **Sidebar**:
   - View top 5 performers
   - See last sync timestamp
   - Refresh data manually

## Files

- `app.py`: Main Streamlit application
- `requirements.txt`: Python dependencies
- `credentials.json`: Google Sheets API credentials (you need to provide this)

## Notes

- The application automatically creates the "Denied Applicants" worksheet if it doesn't exist
- All data changes are immediately synced to Google Sheets
- Caching is implemented to minimize API calls
- The application handles errors gracefully and provides user feedback 