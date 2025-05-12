import streamlit as st
import pandas as pd
import requests
import time
from openai import OpenAI
from openai.error import OpenAIError

# Load secrets
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
SEARCH_ENGINE_ID = st.secrets["SEARCH_ENGINE_ID"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

TAG_COLUMNS = ["HIGH PRIORITY", "NEW JOB", "FAMILY EXPANSION", "LANGUAGE: SPANISH", "CONFIDENCE: LOW"]

def search_google(query):
    try:
        url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={SEARCH_ENGINE_ID}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        items = response.json().get("items", [])
        return [item.get("snippet", "") for item in items]
    except Exception as e:
        st.warning(f"Google Search error for '{query}': {e}")
        return []

def gpt_extract(full_name, snippets):
    if not snippets:
        return None
    text = "\n".join(snippets)
    prompt = f"""
You are assisting a financial advisor. A client named {full_name} appears in the following public data:

{text}

Tasks:
1. List any life events (birth, death, marriage, move), job changes, or languages spoken.
2. Assign a confidence level: High / Medium / Low.
3. Return tags from: HIGH PRIORITY, NEW JOB, FAMILY EXPANSION, LANGUAGE: SPANISH, CONFIDENCE: LOW.
4. Write a warm outreach email referencing any key updates found.

Respond in this format literally:
Summary: ...
Tags: [TAG1, TAG2, ...]
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
    except OpenAIError as e:
        st.warning(f"OpenAI API error for '{full_name}': {e}")
        # Return a default structured string
        return ("Summary: N/A\n"
                "Tags: []\n"
                "Confidence: Low\n"
                "Email: N/A")

def parse_response(result):
    # Initialize defaults
    summary = "N/A"
    tags = []
    confidence = "Low"
    email = "N/A"
    if not result:
        return summary, tags, confidence, email
    # Parse structured response
    try:
        for line in result.split("\n"):
            if line.startswith("Summary:"):
                summary = line.replace("Summary:", "").strip()
            elif line.startswith("Tags:"):
                tags_part = line.replace("Tags:", "").strip().strip("[]")
                tags = [t.strip() for t in tags_part.split(",") if t.strip()]
            elif line.startswith("Confidence:"):
                confidence = line.replace("Confidence:", "").strip()
            elif line.startswith("Email:"):
                email = line.replace("Email:", "").strip()
    except Exception as e:
        st.warning(f"Parsing error: {e}")
    return summary, tags, confidence, email

st.title("Client Intelligence Extractor")
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df["Full Name"] = df["First Name"].fillna("") + " " + df["Last Name"].fillna("")
    # Prepare output columns
    output = df.copy()
    # Raw, Digest, Email and tag columns
    raw_list, summary_list, email_list = [], [], []
    tag_data = {tag: [] for tag in TAG_COLUMNS}

    for _, row in df.iterrows():
        query = f'"{row["Full Name"]}" {row["State"]}'
        snippets = search_google(query)
        time.sleep(1)  # rate control

        raw = "\n".join(snippets) if snippets else "No data"
        raw_list.append(raw)

        result = gpt_extract(row["Full Name"], snippets)
        summary, tags, confidence, email = parse_response(result)

        # Append summary and email
        summary_list.append(f"{summary} (Confidence: {confidence})")
        email_list.append(email)

        # Tag columns
        for tag in TAG_COLUMNS:
            tag_data[tag].append(tag in tags or (tag == "CONFIDENCE: LOW" and confidence.lower() == "low"))

    # Combine into output DataFrame
    output["Raw Data Found"] = raw_list
    output["Digested Summary"] = summary_list
    output["Custom Email Template"] = email_list
    for tag in TAG_COLUMNS:
        output[tag] = tag_data[tag]

    st.success("Enrichment complete.")
    st.dataframe(output)
    st.download_button("Download enriched data as CSV", output.to_csv(index=False), "enriched_clients.csv")