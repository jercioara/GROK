import streamlit as st
from openai import OpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import json
import re

# xAI API setup
xai_api_key = st.secrets.get("XAI_API_KEY", os.getenv("XAI_API_KEY"))
if not xai_api_key:
    st.error("xAI API key not found. Please set the XAI_API_KEY in Streamlit Cloud secrets.")
    st.stop()

xai_client = OpenAI(api_key=xai_api_key, base_url="https://api.x.ai/v1")

# Google API setup
SCOPES = ["https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive"]
creds = None

if "google_credentials" in st.secrets:
    client_secret_dict = json.loads(st.secrets["google_credentials"]["client_secret_json"])
    with open("client_secret.json", "w") as f:
        json.dump(client_secret_dict, f)

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

def create_professional_doc(title, content):
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    requests = []

    # Clean up Markdown artifacts (e.g., remove **, *, >, #)
    content = re.sub(r'[\*#>]+', '', content).strip()

    # Insert all text first, adding extra newlines for spacing
    full_text = content.replace("\n\n", "\n").replace("\n", "\n\n") + "\n\n"
    requests.append({"insertText": {"location": {"index": 1}, "text": full_text}})
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    requests = []

    # Apply professional formatting
    lines = full_text.split("\n")
    index = 1

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            index += 2  # Account for double newline
            continue
        if i == 0:  # Title: centered, bold, larger font
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "paragraphStyle": {"alignment": "CENTER", "spaceBelow": {"magnitude": 12, "unit": "PT"}},
                    "fields": "alignment,spaceBelow"
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "textStyle": {"fontSize": {"magnitude": 16, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,bold,weightedFontFamily"
                }
            })
            index += len(line) + 2
        elif any(line.lower().startswith(x) for x in ["services provided", "services not included", "service level agreement", "term and termination"]):
            # Section headings: bold, slightly larger font, spacing
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "paragraphStyle": {"spaceAbove": {"magnitude": 12, "unit": "PT"}, "spaceBelow": {"magnitude": 6, "unit": "PT"}},
                    "fields": "spaceAbove,spaceBelow"
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "textStyle": {"fontSize": {"magnitude": 12, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,bold,weightedFontFamily"
                }
            })
            index += len(line) + 2
        elif line.startswith("- "):  # Bullet points: proper bullets, indented
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
                }
            })
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "paragraphStyle": {"indentFirstLine": {"magnitude": 18, "unit": "PT"}, "indentStart": {"magnitude": 18, "unit": "PT"}},
                    "fields": "indentFirstLine,indentStart"
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,weightedFontFamily"
                }
            })
            index += len(line) + 2
        else:  # Regular paragraphs: justified, standard spacing
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "paragraphStyle": {"lineSpacing": 115, "alignment": "JUSTIFIED", "spaceAbove": {"magnitude": 6, "unit": "PT"}},
                    "fields": "lineSpacing,alignment,spaceAbove"
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(line)},
                    "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,weightedFontFamily"
                }
            })
            index += len(line) + 2

    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    drive_service.permissions().create(fileId=doc_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

# Streamlit app
st.title("Jeremy's Communication Creator")
topic = st.text_input("What is this communication about:", "I’d like to create an agreement that outlines our Network services at Veeya, what’s in/out, SLA, etc...")

if st.button("Generate Doc"):
    try:
        if not topic:
            st.error("Please enter a topic.")
            st.stop()
        title = "Veeya Network Services Agreement"
        prompt = (
            f"Create a professional agreement for the following topic: '{topic}'. "
            f"Ensure the document is approximately 1 page long. "
            f"Use a formal and professional tone, direct and to the point. "
            f"Include sections for 'Parties Involved', 'Services Provided (What’s In)', 'Services Not Included (What’s Out)', "
            f"'Service Level Agreement (SLA)', and 'Term and Termination'. "
            f"Use bullet points for lists under each section where appropriate."
        )
        content = get_grok_text(prompt)
        url = create_professional_doc(title, content)
        st.success(f"Your document is ready! [Click here to view]({url})")
    except Exception as e:
        st.error(f"Error: {str(e)}")
