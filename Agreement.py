import os
import logging
from flask import Flask, render_template
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from openai import OpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
logging.basicConfig(level=logging.DEBUG)

# Form class
class DocForm(FlaskForm):
    topic = StringField('Topic', validators=[DataRequired()])
    title = StringField('Title (optional)')
    submit = SubmitField('Generate Doc')

# xAI API setup
xai_client = OpenAI(
    api_key="xai-piNOtwpL5Q8Jj0UTcVNkQmbFmujGrflDDlAED5hEp3yOwJ7lddl2ed8wkP7xDrWKMUHIlJr2yfmydLq1",
    base_url="https://api.x.ai/v1"
)

# Google API setup
SCOPES = ["https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive"]
creds = None
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
else:
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    with open("token.json", "w") as token:
        token.write(creds.to_json())

docs_service = build("docs", "v1", credentials=creds)
drive_service = build("drive", "v3", credentials=creds)

def get_grok_text(prompt):
    response = xai_client.chat.completions.create(
        model="grok-2-1212",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500  # Keep it short for a one-page agreement
    )
    return response.choices[0].message.content

def create_fancy_doc(title, content):
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    requests = []

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
        logging.debug(f"Formatting line at index {index}: {line}")
        try:
            if i == 0:  # Title (centered)
                text = line
                requests.append({"updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "paragraphStyle": {"alignment": "CENTER", "spaceBelow": {"magnitude": 12, "unit": "PT"}},
                    "fields": "alignment,spaceBelow"
                }})
                requests.append({"updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "textStyle": {"fontSize": {"magnitude": 14, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,bold,weightedFontFamily"
                }})
                index += len(text) + 1
            elif line.startswith("Clause"):  # Numbered clauses
                text = line
                requests.append({"updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "paragraphStyle": {"indentStart": {"magnitude": 18, "unit": "PT"}, "spaceBelow": {"magnitude": 6, "unit": "PT"}},
                    "fields": "indentStart,spaceBelow"
                }})
                requests.append({"updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,weightedFontFamily"
                }})
                index += len(text) + 1
            elif line.startswith("Signature"):  # Signature lines
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
            else:  # Regular paragraph
                text = line
                requests.append({"updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "paragraphStyle": {"lineSpacing": 115},
                    "fields": "lineSpacing"
                }})
                requests.append({"updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,weightedFontFamily"
                }})
                index += len(text) + 1
        except Exception as e:
            logging.error(f"Error formatting line '{line}' at index {index}: {str(e)}")
            index += len(line) + 1

    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    drive_service.permissions().create(fileId=doc_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

@app.route("/", methods=["GET", "POST"])
def index():
    form = DocForm()
    url = None
    error = None
    if form.validate_on_submit():
        try:
            topic = form.topic.data
            title = form.title.data or f"Settlement Agreement: {topic.split()[0]}"
            prompt = (f"Create a one-page settlement agreement for {topic}. Use a professional yet conversational tone, polished but approachable with a dash of wit and clarity. "
                      "Include a centered title, introductory paragraph, numbered clauses (e.g., Clause 1, Clause 2), and signature lines for both parties. "
                      "Ensure the agreement is concise, fits on one page, and includes all necessary legal details while maintaining readability.")
            content = get_grok_text(prompt)
            url = create_fancy_doc(title, content)
        except Exception as e:
            logging.error(f"Server error: {str(e)}")
            error = str(e)
    return render_template("index.html", form=form, url=url, error=error)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)