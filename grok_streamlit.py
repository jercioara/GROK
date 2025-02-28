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

def create_fancy_doc(title, content):
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    requests = []

    content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)  # Remove asterisks
    full_text = content.replace("\n\n", "\n") + "\n"
    requests.append({"insertText": {"location": {"index": 1}, "text": full_text}})
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    requests = []

    lines = full_text.split("\n")
    index = 1
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            index += 1
            continue
        if i == 0:  # Title
            requests.append({"updateParagraphStyle": {"range": {"startIndex": index, "endIndex": index + len(line)}, "paragraphStyle": {"alignment": "CENTER"}, "fields": "alignment"}})
            requests.append({"updateTextStyle": {"range": {"startIndex": index, "endIndex": index + len(line)}, "textStyle": {"fontSize": {"magnitude": 16, "unit": "PT"}, "bold": True}, "fields": "fontSize,bold"}})
        else:  # Body text
            requests.append({"updateTextStyle": {"range": {"startIndex": index, "endIndex": index + len(line)}, "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}}, "fields": "fontSize"}})
        index += len(line) + 1

    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    drive_service.permissions().create(fileId=doc_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

# Streamlit app
st.title("Jeremy's Communication Creator")

additional_input = st.text_area("Optional: Provide additional context (e.g., original email, Slack message, etc.):", "")
doc_types = ["Formal Agreement / Contract", "Email Response", "Slack / Teams Communication", "Text Message"]
doc_type = st.selectbox("Select the document type:", doc_types)
page_disabled = doc_type in ["Email Response", "Slack / Teams Communication", "Text Message"]
page_options = ["1", "2", "3", "limitless"]
pages = st.selectbox("Select the number of pages:", page_options, disabled=page_disabled)
styles = ["Professional yet conversational", "Formal / professional communication"]
style = st.selectbox("Select the communication style:", styles)
topic = st.text_input("What is this communication about:", "")

if st.button("Generate Doc"):
    try:
        if not topic:
            st.error("Please enter a topic.")
            st.stop()
        title = f"{doc_type}: {topic.split()[0]}"
        if doc_type == "Formal Agreement / Contract":
            length_instruction = f"Ensure the document is {pages} page(s) long." if pages != "limitless" else "No page limit."
        else:
            length_instruction = ""
        style_description = (
            "Use a professional yet conversational tone, polished but approachable with a dash of wit and clarity."
            if style == "Professional yet conversational"
            else "Use a formal and professional tone, direct and to the point."
        )
        prompt = (
            f"Create a {doc_type.lower()} for the following topic: '{topic}'. "
            f"{length_instruction} "
            f"{style_description} "
            f"Include any relevant details from the following context: '{additional_input}'."
        )
        content = get_grok_text(prompt)
        url = create_fancy_doc(title, content)
        st.success(f"Your document is ready! [Click here to view]({url})")
    except Exception as e:
        st.error(f"Error: {str(e)}")
