import os
import logging
from flask import Flask, request, jsonify
from openai import OpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

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
        max_tokens=1000
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
    table_content = []
    table_start = None
    in_table = False

    # Collect table rows
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            if len(cells) >= 2:
                table_content.append(cells[:2])
                if not in_table:
                    in_table = True
                    table_start = index
            else:
                in_table = False
        else:
            in_table = False
        if not in_table and line:
            index += len(line) + 1

    # Apply formatting
    index = 1
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            index += 1
            i += 1
            continue
        logging.debug(f"Formatting line at index {index}: {line}")
        try:
            if line.startswith("|"):
                if table_start == index and table_content:
                    num_rows = min(len(table_content), 4)
                    requests.append({"insertTable": {
                        "rows": num_rows, "columns": 2, "location": {"index": index}
                    }})
                    table_lines = lines[i:i + num_rows]
                    skipped_text = "\n".join(table_lines)
                    index += len(skipped_text) + num_rows
                    i += num_rows
                    for row, cells in enumerate(table_content[:num_rows]):
                        for col, cell in enumerate(cells):
                            cell_index = table_start + (row * 2 + col) * 2
                            requests.append({"insertText": {
                                "location": {"segmentId": "", "tableCellLocation": {"rowIndex": row, "columnIndex": col, "tableStartLocation": {"index": table_start}}},
                                "text": cell
                            }})
                            requests.append({"updateTextStyle": {
                                "range": {"segmentId": "", "startIndex": cell_index, "endIndex": cell_index + len(cell)},
                                "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}, "bold": row == 0},
                                "fields": "fontSize,weightedFontFamily,bold"
                            }})
                    continue
            if line.startswith("# "):
                text = line[2:]
                requests.append({"updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "paragraphStyle": {"namedStyleType": "HEADING_1", "spaceBelow": {"magnitude": 12, "unit": "PT"}},
                    "fields": "namedStyleType,spaceBelow"
                }})
                requests.append({"updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "textStyle": {"fontSize": {"magnitude": 16, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,bold,weightedFontFamily"
                }})
                index += len(text) + 1
            elif line.startswith("## "):
                text = line[3:]
                requests.append({"updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "paragraphStyle": {"namedStyleType": "HEADING_2", "spaceBelow": {"magnitude": 8, "unit": "PT"}},
                    "fields": "namedStyleType,spaceBelow"
                }})
                requests.append({"updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "textStyle": {"fontSize": {"magnitude": 14, "unit": "PT"}, "bold": True, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "fontSize,bold,weightedFontFamily"
                }})
                index += len(text) + 1
            elif line.startswith("> "):
                text = line[2:]
                requests.append({"updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "paragraphStyle": {"indentStart": {"magnitude": 36, "unit": "PT"}, "shading": {"backgroundColor": {"color": {"rgbColor": {"red": 0.95, "green": 0.95, "blue": 0.95}}}}},
                    "fields": "indentStart,shading"
                }})
                requests.append({"updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "textStyle": {"italic": True, "fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "italic,fontSize,weightedFontFamily"
                }})
                index += len(text) + 1
            elif line.startswith("*"):
                text = line.strip("*")
                requests.append({"updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(text)},
                    "textStyle": {"bold": True, "fontSize": {"magnitude": 11, "unit": "PT"}, "weightedFontFamily": {"fontFamily": "Arial"}},
                    "fields": "bold,fontSize,weightedFontFamily"
                }})
                index += len(text) + 1
            else:
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
        i += 1

    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    drive_service.permissions().create(fileId=doc_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

@app.route("/create_doc", methods=["POST"])
def create_doc():
    try:
        data = request.json or {}
        topic = data.get("topic", "Jeremy Cioara’s teaching approach")
        title = data.get("title", f"{topic.capitalize()} Essay")
        prompt = (f"Write a 600-word essay on {topic}. Use a professional yet conversational tone, polished but approachable with a dash of wit and clarity. "
                  "Include # for a title, ## for subheadings, *text* for bold, > for a quote, and a table | Benefit | Impact | for 3 benefits. "
                  "Ensure the table has a header row followed by exactly 3 rows of benefits.")
        content = get_grok_text(prompt)
        url = create_fancy_doc(title, content)
        return jsonify({"url": url})
    except Exception as e:
        logging.error(f"Server error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)