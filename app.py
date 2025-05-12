import streamlit as st
import pandas as pd
import requests
from openai import OpenAI

GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
SEARCH_ENGINE_ID = st.secrets["SEARCH_ENGINE_ID"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

TAG_COLUMNS = ["HIGH PRIORITY", "NEW JOB", "FAMILY EXPANSION", "LANGUAGE: SPANISH", "CONFIDENCE: LOW"]

def search_google(query):
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={SEARCH_ENGINE_ID}"
    response = requests.get(url)
    items = response.json().get("items", [])
    return [item.get("snippet", "") for item in items]

def gpt_extract(full_name, snippets):
    text = "\n".join(snippets)
    prompt = f"""
You are assisting a financial advisor. A client named {full_name} appears in the following recent public data:

{text}

Tasks:
1. List any life events (birth, death, marriage, move), job changes, or language spoken.
2. Assign a confidence level: High / Medium / Low.
3. Return tags from: HIGH PRIORITY, NEW JOB, FAMILY EXPANSION, LANGUAGE: SPANISH, CONFIDENCE: LOW.
4. Write a warm outreach email referencing any key updates found.

Respond in this format:

- Summary: ...
- Tags: ...
- Confidence: ...
- Email: ...
"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return response.choices[0].message.content

def parse_tags(text):
    tag_dict = {tag: False for tag in TAG_COLUMNS}
    if "Tags:" in text:
        tag_line = text.split("Tags:")[1].split("\n")[0]
        for tag in TAG_COLUMNS:
            if tag in tag_line:
                tag_dict[tag] = True
    return tag_dict

st.title("Client Intelligence Extractor")
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df["Full Name"] = df["First Name"] + " " + df["Last Name"]
    raw_data, digests, emails = [], [], []
    tag_data = {tag: [] for tag in TAG_COLUMNS}

    for _, row in df.iterrows():
        query = f'"{row["Full Name"]}" {row["State"]}'
        snippets = search_google(query)
        if not snippets:
            raw_data.append("No data found")
            digests.append("N/A")
            emails.append("N/A")
            for tag in TAG_COLUMNS:
                tag_data[tag].append(False)
            continue

        result = gpt_extract(row["Full Name"], snippets)
        raw_data.append("\n".join(snippets))
        digests.append(result.split("Summary:")[1].split("Tags:")[0].strip() if "Summary:" in result else "N/A")
        emails.append(result.split("Email:")[1].strip() if "Email:" in result else "N/A")

        tag_flags = parse_tags(result)
        for tag in TAG_COLUMNS:
            tag_data[tag].append(tag_flags[tag])

    df["Raw Data Found"] = raw_data
    df["Digested Summary"] = digests
    df["Custom Email Template"] = emails
    for tag in TAG_COLUMNS:
        df[tag] = tag_data[tag]

    st.success("Enrichment complete.")
    st.dataframe(df)
    st.download_button("Download Enriched File", df.to_csv(index=False), "enriched_clients.csv")
