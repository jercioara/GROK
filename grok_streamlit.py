import streamlit as st
from openai import OpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
import os
import json
import io
import re

# xAI API setup
xai_api_key = st.secrets.get("XAI_API_KEY", os.getenv("XAI_API_KEY"))
if not xai_api_key:
    st.error("xAI API key not found. Please set the XAI_API_KEY in Streamlit Cloud secrets.")
    st.stop()

xai_client = OpenAI(
    api_key=xai_api_key,
    base_url="https://api.x.ai/v1"
)

# Google API setup
SCOPES = ["https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive"]
creds = None

# Load client_secret.json from Streamlit secrets
if "google_credentials" in st.secrets:
    client_secret_dict = json.loads(st.secrets["google_credentials"]["client_secret_json"])
    with open("client_secret.json", "w") as f:
        json.dump(client_secret_dict, f)
else:
    st.error("Google API credentials not found. Please add client_secret_json to Streamlit Cloud secrets.")
    st.stop()

# Load token.json from Streamlit secrets
if "google_credentials" in st.secrets and "token_json" in st.secrets["google_credentials"]:
    token_dict = json.loads(st.secrets["google_credentials"]["token_json"])
    with open("token.json", "w") as f:
        json.dump(token_dict, f)
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
else:
    st.error("Please add token_json to Streamlit Cloud secrets under google_credentials.")
    st.stop()

docs_service = build("docs", "v1", credentials=creds)
drive_service = build("drive", "v3", credentials=creds)

def get_grok_text(prompt):
    response = xai_client.chat.completions.create(
        model="grok-2-1212",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )
    return response.choices[0].message.content

def create_fancy_doc(title, content):
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    requests = []

    # Clean up asterisks from the content (e.g., **Clause 1** -> Clause 1)
    content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)

    # Insert all text first
    full_text = content.replace("\n\n", "\n") + "\n"
    requests.append({"insertText": {"location": {"index": 1}, "text": full_text}})
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    requests = []

    # Apply formatting
    lines = full_text.split("\n")
    index = 1

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            index += 1
            continue
        if i == 0:  # Title (centered, larger font, bold)
            text = line
            requests.append({"updateParagraphStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text)},
                "paragraphStyle": {"alignment": "CENTER", "spaceBelow": {"magnitude": 12, "unit": "PT"}},
                "fields": "alignment,spaceBelow"
            }})
            requests.append({"updateTextStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text)},
                "textStyle": {"fontSize": {"magnitude": 16, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                "fields": "fontSize,bold,weightedFontFamily"
            }})
            index += len(text) + 1
        elif line.lower().startswith("clause"):  # Clauses (bold, slightly larger font)
            text = line
            requests.append({"updateParagraphStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text)},
                "paragraphStyle": {"spaceAbove": {"magnitude": 8, "unit": "PT"}, "spaceBelow": {"magnitude": 6, "unit": "PT"}},
                "fields": "spaceAbove,spaceBelow"
            }})
            requests.append({"updateTextStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text)},
                "textStyle": {"fontSize": {"magnitude": 12, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                "fields": "fontSize,bold,weightedFontFamily"
            }})
            index += len(text) + 1
        elif line.lower().startswith("signature"):  # Signature lines (normal text, more space above)
            text = line
            requests.append({"updateParagraphStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text)},
                "paragraphStyle": {"spaceAbove": {"magnitude": 12, "unit": "PT"}},
                "fields": "spaceAbove"
            }})
            requests.append({"updateTextStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text)},
                "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                "fields": "fontSize,weightedFontFamily"
            }})
            index += len(text) + 1
        else:  # Regular paragraph (normal text, justified, 1.15 spacing)
            text = line
            requests.append({"updateParagraphStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text)},
                "paragraphStyle": {"lineSpacing": 115, "alignment": "JUSTIFIED"},
                "fields": "lineSpacing,alignment"
            }})
            requests.append({"updateTextStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text)},
                "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                "fields": "fontSize,weightedFontFamily"
            }})
            index += len(text) + 1

    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    drive_service.permissions().create(fileId=doc_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

# Streamlit app
st.title("Grok Doc Generator v2")
topic = st.text_input("Enter your topic:", "Settlement agreement placeholder")
title = st.text_input("Enter a title (optional):", "")
if st.button("Generate Doc"):
    try:
        if not title:
            title = f"Settlement Agreement: {topic.split()[0]}"
        prompt = (f"Create a one-page settlement agreement for {topic}. Use a professional yet conversational tone, polished but approachable with a dash of wit and clarity. "
                  "Include a centered title, introductory paragraph, numbered clauses (e.g., Clause 1, Clause 2), and signature lines for both parties. "
                  "Ensure the agreement is concise, fits on one page, and includes all necessary legal details while maintaining readability.")
        content = get_grok_text(prompt)
        url = create_fancy_doc(title, content)
        st.success(f"Your document is ready! [Click here to view]({url})")
    except Exception as e:
        st.error(f"Error: {str(e)}")
