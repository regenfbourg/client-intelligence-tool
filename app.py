import streamlit as st
import pandas as pd
import requests
import time
from openai import OpenAI

# Load secrets
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
SEARCH_ENGINE_ID = st.secrets["SEARCH_ENGINE_ID"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

TAG_COLUMNS = ["HIGH PRIORITY", "NEW JOB", "FAMILY EXPANSION", "MOVED", "CONFIDENCE: LOW"]
MAX_QUERIES = 90
query_count = 0

def build_query(full_name, state):
    base = f'"{full_name}" {state}'
    life_signals = (
        '"joined" OR "promoted" OR "baby" OR "welcomed a baby" OR "passed away" OR '
        '"got married" OR "wedding" OR "moved to" OR "bought a home"'
    )
    trusted_sites = (
        "site:linkedin.com/in OR site:legacy.com OR site:tributearchive.com OR "
        "site:theknot.com OR site:zola.com OR site:babylist.com OR site:zillow.com OR site:redfin.com"
    )
    return f'{base} ({life_signals}) {trusted_sites}'

def search_google(query):
    global query_count
    if query_count >= MAX_QUERIES:
        return ["Search limit reached. No further queries sent."]
    try:
        url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={SEARCH_ENGINE_ID}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        query_count += 1
        items = response.json().get("items", [])
        return [item.get("snippet", "") for item in items]
    except Exception as e:
        st.warning(f"Google Search error: {e}")
        return []

def gpt_extract(full_name, snippets):
    text = "\n".join(snippets)
    prompt = f"""
You are a research assistant for a financial advisor. Below is public data found online about a client named {full_name}:

{text}

Your tasks:
1. Identify life events: marriage, birth, death, move/new home.
2. Identify any job events: job changes, promotions.
3. Guess spoken languages if relevant.
4. Assign a confidence level (High / Medium / Low).

Return this format:
Summary: ...
Tags: [HIGH PRIORITY, NEW JOB, FAMILY EXPANSION, MOVED, CONFIDENCE: LOW]
Confidence: ...
Email: ...
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        st.warning(f"OpenAI error for {full_name}: {e}")
        return "Summary: No major updates.\nTags: []\nConfidence: Low\nEmail: Just checking in!"

def parse_response(result):
    summary = "N/A"
    tags = []
    confidence = "Low"
    email = "N/A"
    try:
        for line in result.split("\n"):
            if line.startswith("Summary:"):
                summary = line.replace("Summary:", "").strip()
            elif line.startswith("Tags:"):
                tags_line = line.replace("Tags:", "").strip().strip("[]")
                tags = [t.strip() for t in tags_line.split(",") if t.strip()]
            elif line.startswith("Confidence:"):
                confidence = line.replace("Confidence:", "").strip()
            elif line.startswith("Email:"):
                email = line.replace("Email:", "").strip()
    except Exception as e:
        st.warning(f"Parsing error: {e}")
    return summary, tags, confidence, email

st.title("Expanded Life Event Insight Extractor")
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df["Full Name"] = df["First Name"].fillna("") + " " + df["Last Name"].fillna("")
    output = df.copy()
    raw_list, summary_list, email_list = [], [], []
    tag_data = {tag: [] for tag in TAG_COLUMNS}

    for _, row in df.iterrows():
        query = build_query(row["Full Name"], row["State"])
        snippets = search_google(query)
        time.sleep(1)

        raw = "\n".join(snippets) if snippets else "No data"
        raw_list.append(raw)

        result = gpt_extract(row["Full Name"], snippets)
        summary, tags, confidence, email = parse_response(result)

        summary_list.append(f"{summary} (Confidence: {confidence})")
        email_list.append(email)

        for tag in TAG_COLUMNS:
            tag_data[tag].append(tag in tags or (tag == "CONFIDENCE: LOW" and confidence.lower() == "low"))

    output["Raw Data Found"] = raw_list
    output["Digested Summary"] = summary_list
    output["Custom Email Template"] = email_list
    for tag in TAG_COLUMNS:
        output[tag] = tag_data[tag]

    st.success("✅ Expanded enrichment complete.")
    st.dataframe(output)
    st.download_button("📥 Download CSV", output.to_csv(index=False), "enriched_clients_life_events.csv")