import streamlit as st
from openai import OpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import json

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

def generate_prompt(doc_type, topic, additional_input, pages):
    """Generate a prompt that reflects the user's stylistic principles."""
    base_prompt = "Generate a {doc_type} for this topic: '{topic}'. "
    style_instruction = (
        "Write in a professional yet conversational tone—polished, approachable, and with a sprinkle of wit. "
        "Keep the language clear and concise, skipping unnecessary jargon. Engage the reader with inclusive language like 'we' or 'you,' "
        "and weave in subtle humor or playful metaphors where it fits."
    )
    structure_instruction = {
        "Formal Agreement / Contract": (
            "Organize it with clear headings and numbered clauses for a sharp, readable structure. "
            "Make it practical and to the point, with a friendly nudge to keep things smooth between us."
        ),
        "Email Response": (
            "Start with 'Subject: ' followed by a punchy subject line, then a concise, engaging body. "
            "Address the recipient directly and wrap it up with a positive vibe."
        ),
        "Slack / Teams Communication": (
            "Keep it short and snappy, perfect for a team chat. Add a dash of personality but stay专业—think casual yet sharp."
        ),
        "Text Message": (
            "Make it brief and clear, with a touch of informal flair. Get the point across fast."
        )
    }
    length_instruction = ""
    if doc_type == "Formal Agreement / Contract" and pages != "limitless":
        length_instruction = f"Stretch it to about {pages} page(s), give or take—make it feel complete but not overstuffed. "
    context_instruction = "Weave in any relevant bits from this context: '{additional_input}'."
    return (
        base_prompt.format(doc_type=doc_type) +
        style_instruction + " " +
        structure_instruction.get(doc_type, "") + " " +
        length_instruction +
        context_instruction.format(additional_input=additional_input)
    )

def get_grok_text(prompt):
    """Fetch text from Grok with the styled prompt."""
    response = xai_client.chat.completions.create(
        model="grok-2-1212",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )
    return response.choices[0].message.content

def create_professional_doc(title, content, doc_type):
    """Create a Google Doc with formatting that matches the user's structured style."""
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    requests = []

    # Insert all text first
    full_text = content + "\n"
    requests.append({"insertText": {"location": {"index": 1}, "text": full_text}})
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    requests = []

    if doc_type == "Formal Agreement / Contract":
        lines = full_text.split("\n")
        index = 1
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            start_index = index
            end_index = index + len(line)
            if i == 0:  # Title
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": start_index, "endIndex": end_index},
                        "paragraphStyle": {"alignment": "CENTER"},
                        "fields": "alignment"
                    }
                })
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": start_index, "endIndex": end_index},
                        "textStyle": {"fontSize": {"magnitude": 14, "unit": "PT"}, "bold": True},
                        "fields": "fontSize,bold"
                    }
                })
            elif line.lower().startswith("clause") or line[0].isdigit():  # Headings
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": start_index, "endIndex": end_index},
                        "paragraphStyle": {"namedStyleType": "HEADING_2"},
                        "fields": "namedStyleType"
                    }
                })
            elif line.startswith("-"):  # Bullet points
                requests.append({
                    "createParagraphBullets": {
                        "range": {"startIndex": start_index, "endIndex": end_index},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
                    }
                })
            else:  # Regular text
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": start_index, "endIndex": end_index},
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "fields": "namedStyleType"
                    }
                })
            index = end_index + 1

    elif doc_type == "Email Response":
        lines = full_text.split("\n", 1)
        if len(lines) > 1:
            subject = lines[0].strip()
            body = lines[1].strip()
            subject_start = 1
            subject_end = subject_start + len(subject)
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": subject_start, "endIndex": subject_end},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType"
                }
            })
            body_start = subject_end + 1
            body_end = body_start + len(body)
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": body_start, "endIndex": body_end},
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "fields": "namedStyleType"
                }
            })
        else:
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": 1, "endIndex": len(full_text) + 1},
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "fields": "namedStyleType"
                }
            })

    else:  # Slack / Teams Communication and Text Message
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": len(full_text) + 1},
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "fields": "namedStyleType"
            }
        })

    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    drive_service.permissions().create(fileId=doc_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

# Streamlit app
st.title("Jeremy's Communication Creator")
additional_input = st.text_area("Optional: Add some context (e.g., an email to riff on, a situation to address):", "")
doc_types = ["Formal Agreement / Contract", "Email Response", "Slack / Teams Communication", "Text Message"]
doc_type = st.selectbox("Pick your document type:", doc_types)
page_disabled = doc_type in ["Email Response", "Slack / Teams Communication", "Text Message"]
page_options = ["1", "2", "3", "limitless"]
pages = st.selectbox("How many pages? (Only for agreements):", page_options, disabled=page_disabled)
topic = st.text_input("What’s this communication about:", "")

if st.button("Generate Doc"):
    if not topic:
        st.error("Give me a topic to work with!")
        st.stop()
    prompt = generate_prompt(doc_type, topic, additional_input, pages)
    content = get_grok_text(prompt)
    url = create_professional_doc(topic, content, doc_type)
    st.success(f"Your doc’s ready! [Check it out here]({url})")
