import streamlit as st
import fitz  # PyMuPDF for extracting text from PDFs
import pytesseract
import cv2
import re
import json
import hashlib
import sqlite3
import requests
from PIL import Image

# Configuration
GROQ_API_KEY = "Your_api_key"
API_URL = "your_api_url"

# Initialize Database
def init_db():
    conn = sqlite3.connect("documents.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT UNIQUE,
            date TEXT,
            amount TEXT,
            organization TEXT,
            summary TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT UNIQUE,
            applicant_name TEXT,
            loan_amount TEXT,
            loan_reason TEXT,
            summary TEXT
        )
    """)
    conn.commit()
    conn.close()

# Generate unique hash for document
def generate_file_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()

# Extract text from PDF using PyMuPDF
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text") + "\n"
    return text.strip()

# Extract text from scanned PDFs using PyMuPDF and OCR
def extract_text_from_scanned_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    full_text = ""
    for page_num in range(len(doc)):
        pix = doc[page_num].get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img = img.convert("L")  # Convert to grayscale for better OCR
        text = pytesseract.image_to_string(img)
        full_text += text + "\n"
    return full_text.strip()

# Extract key details from invoice
def extract_invoice_details(text):
    details = {}
    date_pattern = r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}-\d{2}-\d{2})\b'
    details["Dates"] = re.findall(date_pattern, text) or "Not found"

    money_pattern = r'₹?\$?\d{1,3}(?:,?\d{3})*(?:\.\d{2})?'
    details["Amount"] = re.findall(money_pattern, text) or "Not found"

    org_pattern = r'\b(?:[A-Z][a-zA-Z0-9&., ]* (?:Bank|Ltd|Corp|Company|LLC|Inc|Finance|Credit|Services))\b'
    details["Organizations"] = list(set(re.findall(org_pattern, text))) or "Not found"

    return details

# Extract key details from loan application
def extract_loan_details(text):
    details = {}
    name_pattern = r'^[A-Z][a-z]+\s[A-Z][a-z]+'
    name_match = re.search(name_pattern, text)
    details["Applicant Name"] = name_match.group() if name_match else "Not found"

    money_pattern = r'₹?\$?\d{1,3}(?:,?\d{3})*(?:\.\d{2})?'
    details["Loan Amount"] = re.findall(money_pattern, text) or "Not found"

    reason_keywords = ["home", "education", "business", "medical", "vehicle", "personal"]
    for word in reason_keywords:
        if word in text.lower():
            details["Loan Reason"] = word.capitalize()
            break
    else:
        details["Loan Reason"] = "Not found"

    return details

# Summarize using Groq API
def summarize_text(text, prompt_type):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    if prompt_type == "invoice":
        prompt = f"Summarize this invoice, highlighting key details:\n\n{text}"
    else:
        prompt = f"Summarize this loan application, explaining the reason and key details:\n\n{text}"
    
    data = {
        "model": "mixtral-8x7b-32768",
        "messages": [{"role": "system", "content": "You are an AI summarizing documents."},
                     {"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 500
    }
    
    response = requests.post(API_URL, headers=headers, json=data)
    
    if response.status_code == 200:
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "No summary generated.")
    else:
        return f"Error: {response.status_code}, {response.text}"

# Store invoice in database
def store_invoice(file_hash, details, summary):
    conn = sqlite3.connect("documents.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO invoices (file_hash, date, amount, organization, summary) VALUES (?, ?, ?, ?, ?)",
                  (file_hash, str(details["Dates"]), str(details["Amount"]), str(details["Organizations"]), summary))
        conn.commit()
        st.success("✅ Invoice saved to database!")
    except sqlite3.IntegrityError:
        st.warning("⚠ Duplicate invoice detected! Not saving to database.")
    conn.close()

# Store loan application in database
def store_loan(file_hash, details, summary):
    conn = sqlite3.connect("documents.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO loans (file_hash, applicant_name, loan_amount, loan_reason, summary) VALUES (?, ?, ?, ?, ?)",
                  (file_hash, details["Applicant Name"], str(details["Loan Amount"]), details["Loan Reason"], summary))
        conn.commit()
        st.success("✅ Loan application saved to database!")
    except sqlite3.IntegrityError:
        st.warning("⚠ Duplicate loan detected! Not saving to database.")
    conn.close()

# Streamlit UI
st.sidebar.title("Document Summarization 📄")
option = st.sidebar.radio("Choose Document Type:", ["Invoice Summarization", "Loan Application Summarization"])
st.title(option)

# About Section
st.sidebar.markdown("""
### 📌 About This App  
This tool extracts and summarizes key details from *invoices* and *loan applications* using *AI-powered text extraction* and *summarization models*.  

✅ Supports *scanned & digital PDFs*  
✅ Uses *OCR for text extraction*  
✅ Stores *document data in a database*  
✅ Powered by *Groq AI for summarization*  

🔍 *Select a document type* to get started!
""")

# Initialize the database
init_db()

uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])
summary = ""

if uploaded_file:
    file_path = "uploaded_file.pdf"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.read())

    st.info("🔍 Extracting text...")

    text = extract_text_from_pdf(file_path) or extract_text_from_scanned_pdf(file_path)

    if text:
        st.success("✅ Text extracted successfully!")
        st.text_area("Extracted Text:", text, height=250)

        if option == "Invoice Summarization":
            details = extract_invoice_details(text)
            summary = summarize_text(text, "invoice")
            store_invoice(generate_file_hash(text), details, summary)
        else:
            details = extract_loan_details(text)
            summary = summarize_text(text, "loan")
            store_loan(generate_file_hash(text), details, summary)

        st.subheader("Summary")
        st.write(summary)

# Chatbot - Answer user questions based on document content
if summary:
    user_input = st.sidebar.chat_input("Ask about the document summary...")
    if user_input:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        chat_data = {
            "model": "mixtral-8x7b-32768",
            "messages": [{"role": "system", "content": "You are an AI assistant helping users understand documents."},
                         {"role": "user", "content": f"Document summary:\n{summary}"},
                         {"role": "user", "content": user_input}],
            "temperature": 0.7,
            "max_tokens": 500
        }

        response = requests.post(API_URL, headers=headers, json=chat_data)

        st.sidebar.write("💬 Chatbot:", response.json().get("choices", [{}])[0].get("message", {}).get("content", "I couldn't find an answer."))
    