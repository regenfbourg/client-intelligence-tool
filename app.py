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

TAG_COLUMNS = ["HIGH PRIORITY", "NEW JOB", "FAMILY EXPANSION", "MOVED", "LANGUAGE: SPANISH", "CONFIDENCE: LOW"]
MAX_QUERIES = 90
query_count = 0

def build_query(full_name, state):
    base = f'"{full_name}" {state}'
    enriched_keywords = (
        '"joined" OR "promoted" OR "hired" OR "now at" OR "currently at" OR "recently started" OR "new position" OR "new role" OR "baby" OR "welcomed a baby" OR '
        '"passed away" OR "obituary" OR "married" OR "wedding" OR "moved to" OR "bought a home" OR '
        '"relocated" OR "speaks Spanish" OR "conference speaker" OR "panelist" OR "honored" OR "featured"'
    )
    enriched_sites = (
        "site:linkedin.com/in OR site:linkedin.com/pub OR site:linkedin.com/company OR site:legacy.com OR site:tributearchive.com OR "
        "site:theknot.com OR site:zola.com OR site:babylist.com OR site:zillow.com OR site:redfin.com OR "
        "site:news.ycombinator.com OR site:techcrunch.com OR site:medium.com OR site:substack.com OR "
        "site:conference-board.org OR site:eventbrite.com OR site:forbes.com OR site:bloomberg.com"
    )
    return f'{base} ({enriched_keywords}) {enriched_sites}'

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
1. Identify life events: marriage, birth, death, move, home purchase.
2. Identify professional events: promotions, new jobs, speaking engagements, media features.
3. Identify languages spoken.
4. Assign a confidence level (High / Medium / Low).
5. Tag the person from: HIGH PRIORITY, NEW JOB, FAMILY EXPANSION, MOVED, LANGUAGE: SPANISH, CONFIDENCE: LOW.

Return this format:
Summary: ...
Tags: [ ... ]
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

st.title("Full-Scope Life & Career Insight Extractor")
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
    st.download_button("📥 Download CSV", output.to_csv(index=False), "full_enriched_clients.csv")