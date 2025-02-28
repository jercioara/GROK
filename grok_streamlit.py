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

    # Split content into lines
    lines = content.split("\n")
    # Filter out empty lines and strip whitespace
    lines = [line.strip() for line in lines if line.strip()]
    # Join lines with double newlines for consistent spacing
    full_text = "\n\n".join(lines)
    # Remove trailing newlines to avoid index issues
    full_text = full_text.rstrip("\n") + "\n"
    requests.append({"insertText": {"location": {"index": 1}, "text": full_text}})
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    requests = []

    # Calculate total document length
    doc_length = len(full_text)
    current_position = 1  # Start at index 1 (Google Docs indices start at 1)

    # Apply professional formatting
    for i, line in enumerate(lines):
        # Calculate the range for this line
        start_index = current_position
        end_index = start_index + len(line)

        # Debugging: Log the indices for this line
        print(f"Line {i}: '{line}', start_index={start_index}, end_index={end_index}, doc_length={doc_length}")

        # Ensure indices are within document bounds and valid
        if start_index >= doc_length:
            print(f"Warning: start_index {start_index} exceeds document length {doc_length}. Stopping.")
            break
        if end_index > doc_length:
            print(f"Warning: end_index {end_index} exceeds document length {doc_length}. Adjusting.")
            end_index = doc_length
        if start_index >= end_index:
            print(f"Invalid range: start_index={start_index}, end_index={end_index}. Skipping.")
            continue

        # Apply formatting based on line type
        if i == 0:  # Title: centered, bold, larger font
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "paragraphStyle": {"alignment": "CENTER", "spaceBelow": {"magnitude": 12, "unit": "PT"}},
                    "fields": "alignment,spaceBelow"
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "textStyle": {"fontSize": {"magnitude": 16, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,bold,weightedFontFamily"
                }
            })
        elif any(line.lower().startswith(x.lower()) for x in [
            "parties involved", "services provided", "services not included", 
            "service level agreement", "term and termination"
        ]):
            # Section headings: bold, slightly larger font, spacing
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "paragraphStyle": {"spaceAbove": {"magnitude": 12, "unit": "PT"}, "spaceBelow": {"magnitude": 6, "unit": "PT"}},
                    "fields": "spaceAbove,spaceBelow"
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "textStyle": {"fontSize": {"magnitude": 12, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,bold,weightedFontFamily"
                }
            })
        elif line.startswith("- "):  # Bullet points: proper bullets, indented
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
                }
            })
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "paragraphStyle": {"indentFirstLine": {"magnitude": 18, "unit": "PT"}, "indentStart": {"magnitude": 18, "unit": "PT"}},
                    "fields": "indentFirstLine,indentStart"
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,weightedFontFamily"
                }
            })
        else:  # Regular paragraphs: justified, standard spacing
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "paragraphStyle": {"lineSpacing": 115, "alignment": "JUSTIFIED", "spaceAbove": {"magnitude": 6, "unit": "PT"}},
                    "fields": "lineSpacing,alignment,spaceAbove"
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,weightedFontFamily"
                }
            })
        # Update the position for the next line
        current_position = end_index + 2  # Account for \n\n between lines

    if requests:
        # Debug: Log the number of requests
        print(f"Total requests: {len(requests)}")
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
    if not topic:
        st.error("Please enter a topic.")
        st.stop()
    title = f"{doc_type}: {topic.split()[0]}"
    if doc_type == "Formal Agreement / Contract":
        length_instruction = f"Ensure the document is {pages} page(s) long." if pages != "limitless" else "No page limit."
        prompt = (
            f"Create a {doc_type.lower()} for the following topic: '{topic}'. "
            f"{length_instruction} "
            f"Use a professional yet conversational tone, polished but approachable with a dash of wit and clarity. "
            f"Include sections for 'Parties Involved', 'Services Provided (What’s In)', 'Services Not Included (What’s Out)', "
            f"'Service Level Agreement (SLA)', and 'Term and Termination'. "
            f"Use bullet points for lists under each section where appropriate. "
            f"Include any relevant details from the following context: '{additional_input}'."
        )
    else:
        length_instruction = ""
        prompt = (
            f"Create a {doc_type.lower()} for the following topic: '{topic}'. "
            f"{length_instruction} "
            f"Use a professional yet conversational tone, polished but approachable with a dash of wit and clarity. "
            f"Include any relevant details from the following context: '{additional_input}'."
        )
    try:
        content = get_grok_text(prompt)
        url = create_professional_doc(title, content)
        st.success(f"Your document is ready! [Click here to view]({url})")
    except Exception as e:
        st.error(f"Error: {str(e)}")
