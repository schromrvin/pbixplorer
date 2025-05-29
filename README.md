# PBIXplorer: Power BI File Analyzer & Chatbot 🤖🔍 (PBIT & PBIX)

[![Python Version](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.20%2B-FF4B4B.svg)](https://streamlit.io)
[![Gemini API](https://img.shields.io/badge/Gemini%20API-Required-green.svg)](https://ai.google.dev/)

**PBIXplorer** is an advanced local Streamlit application designed to parse, analyze, and explore Power BI Template (`.pbit`) and Power BI Desktop (`.pbix`) files. It features a sophisticated chatbot powered by Google's Gemini API, allowing users to interact with file metadata, ask analytical questions about the data, and get insights in a conversational manner. The app also includes a structured metadata explorer.

**All PBIT/PBIX file processing and initial metadata extraction happen locally. The Gemini API is used for the chatbot's natural language understanding and analytical response generation.**

## ✨ Features

*   **Dual File Type Support:**
    *   Parses both `.pbit` (Power BI Template) and `.pbix` (Power BI Desktop) files.
    *   Local extraction of `DataModelSchema` (for PBIT) and decompression/parsing of `DataModel` (for PBIX using PBIXRay components).
    *   Handles various text encodings and BOMs for internal JSON files.
*   **Comprehensive Metadata Extraction:**
    *   **Data Model (PBIT & PBIX):** Tables, columns (with data types), DAX measures (with formulas), calculated columns (with formulas), and relationships.
    *   **M Queries (Power Query - PBIT & PBIX):** Extracts M scripts and performs basic analysis (source/transformation identification).
    *   **Report Structure (PBIT & PBIX if available):** Parses `Report/Layout` to extract pages, visuals (type, title), and fields used.
    *   **PBIX Data Previews:** Extracts and displays sample rows from tables within PBIX files.
*   **Interactive Gemini-Powered Chatbot ("PBIXplorer"):**
    *   **Natural Language Queries:** Ask complex questions about file metadata, data content, and perform AI-assisted analysis.
        *   "List all tables and their column counts."
        *   "What's the DAX formula for the 'Total Sales' measure in the 'FactSales' table?"
        *   "Show me the M query for the 'DimProduct' table."
        *   "What visuals are on the 'Sales Overview' page and what fields do they use?"
        *   "Analyze the monthly revenue trend based on the 'OrderDate' and 'Revenue' in the 'Sales' table."
        *   "What are common KPIs for e-commerce dashboards?" (General knowledge)
        *   "Based on the product categories and sales samples, which category seems to be performing best?"
    *   **Conversational Context:** Remembers previous turns of the conversation for follow-up questions.
    *   **Retrieval Augmented Generation (RAG) / Tool Use:**
        *   Gemini receives initial metadata and small data samples (first ~10 rows per table for PBIX).
        *   If more data is needed for analysis, PBIXplorer can "request" specific tables.
        *   The application then fetches a larger sample (first ~200 rows) of the requested table(s) and re-prompts Gemini for a more detailed analysis.
    *   **Markdown Formatted Responses:** Chatbot responses are structured with Markdown for enhanced readability.
*   **Metadata Explorer (Sidebar):**
    *   Browse extracted metadata in a structured, searchable view:
        *   Tables & Columns
        *   Measures (with DAX)
        *   Calculated Columns (with DAX)
        *   Relationships
        *   M Queries (with script and analysis)
        *   Report Structure (Pages > Visuals > Fields)
        *   **PBIX Table Data:** Directly view the first 100 rows of any table from a loaded PBIX file within the sidebar.
    *   Search functionality within most explorer categories.
*   **Local Processing for File Parsing:** Core file unpacking and metadata structuring occur locally. API calls are made to Gemini for NLU and response generation.

## Demo Streamlit App 👨‍💻

You can test the app hosted at **https://pbixplorer.streamlit.app/**.

*(sample .pbit/.pbix files can be found in the [templates](templates) folder of the repository)*

## 🤔 Why PBIXplorer?

*   **Deep Insights:** Go beyond basic metadata. Understand data relationships, DAX logic, M transformations, and get AI-assisted analysis of your Power BI files.
*   **PBIX Data Exploration:** Directly view samples of imported data within PBIX files without needing Power BI Desktop.
*   **Enhanced Debugging & Documentation:** Quickly find where fields are used, understand complex calculations, and extract information for documentation.
*   **Learning & Exploration:** A powerful tool to learn how Power BI reports and data models are constructed and to explore data patterns with AI assistance.

## 🛠️ Tech Stack

*   **Python 3.9+** (Required for modern Gemini API library)
*   **Streamlit:** For the web application interface.
*   **Google Generative AI SDK (`google-generativeai`):** For interacting with the Gemini API.
*   **Pandas:** For data manipulation and display.
*   **PBIXRay (components):** For unpacking and decoding PBIX `DataModel` files. Includes dependencies like `apsw` (for SQLite) and `kaitaistruct` (for parsing binary formats).
*   **Standard Python libraries:** `zipfile`, `json`, `os`, `re`, `codecs`, `tempfile`.

## 📁 File Structure (Simplified)
```
PBIXplorer-analyzer/
├── pbixray_lib/ # PBIXRay library components
├── templates/ # Sample .pbit/.pbix files for testing
├── .gitignore
├── app.py # Main Streamlit application
├── chatbot_logic.py # Gemini API interaction, prompt construction, RAG logic
├── pbit_parser.py # Parses .pbit metadata and Report/Layout from .pbix
├── README.md # This file
└── requirements.txt # Python dependencies
```

## 🚀 Setup & Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/schromrvin/pbixplorer pbixplorer
    cd pbixplorer
    ```

2.  **Python Environment (Python 3.9+ Recommended):**
    Create and activate a virtual environment:
    ```bash
    # Example using Python 3.9
    python3.9 -m venv venv
    # Activate:
    # Windows: venv\Scripts\activate
    # macOS/Linux: source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```
    *   **Note on `xpress9`:** PBIXRay relies on the `xpress9` decompression library, which might need separate installation steps depending on your OS if not handled by `pip` directly.
    *   **Note on `apsw`:** This SQLite wrapper often requires build tools. If `pip install apsw` fails, consult `apsw` installation guides for your OS.

4.  **Get a Gemini API Key:**
    *   Visit [Google AI Studio (makersuite.google.com)](https://makersuite.google.com/) to get your API key.

## ▶️ Running the Application

1.  **Activate your virtual environment.**
2.  **Run the Streamlit application from the project root directory:**
    ```bash
    streamlit run app.py
    ```
    This will open the application in your web browser.

3.  **Configure API Key:**
    *   On first run, or if the key is not set, PBIXplorer will prompt you to enter your Gemini API Key in the sidebar.

## 📖 How to Use

1.  **Launch & Configure:** Run the app and enter your Gemini API Key in the sidebar.
2.  **Upload File:** Use the file uploader in the sidebar to choose a `.pbit` or `.pbix` file.
3.  **Wait for Processing:** The app will parse the file and prepare the context for Gemini. Success/error messages appear in the sidebar. An initial greeting from PBIXplorer will appear in the chat.
4.  **Interact:**
    *   **PBIXplorer Chatbot (Main Area):**
        *   Type your questions about the file's metadata, data content, or ask for analysis.
        *   If PBIXplorer needs more data from specific PBIX tables for your query, it will inform you and then automatically "fetch" a larger sample of those tables to continue the analysis.
    *   **Metadata Explorer (Sidebar):**
        *   Select a category (e.g., "Tables & Columns", "Measures", "View Table Data (Sidebar)").
        *   Use the search box to filter items within most categories.
        *   Expand items for details (e.g., DAX formulas, M scripts).
        *   For PBIX files, "View Table Data (Sidebar)" shows the first 100 rows of selected tables.

## 🚧 Limitations & Future Work

*   **Token Limits & Performance with Large Files:**
    *   While `gemini-2.5-flash-preview-05-20` has a large context window, extremely complex files with numerous tables/measures or very long chat histories might still approach token limits for the API calls.
    *   Fetching and processing data for the RAG system involves local computation; very large PBIX tables might take a moment for `get_table()` to execute.
*   **Depth of AI Analysis:** Gemini's analysis is based on the (sampled) data provided. For highly complex statistical modeling or enterprise-scale data processing, dedicated BI tools remain superior. PBIXplorer aims for AI-assisted insights.
*   **M Query Parsing:** PBIT/PBIX M query analysis is still primarily based on pattern matching from the `pbit_parser.py` and direct script extraction for PBIXRay; full M language parsing is out of scope.
*   **PBIX Report/Layout Nuances:** Parsing of `Report/Layout` for PBIX might not capture all visual configurations or custom visual details as deeply as Power BI Desktop.

**Potential Future Enhancements:**

*   **More Advanced RAG:**
    *   Smarter data summarization techniques (e.g., `df.describe()`, value counts for categoricals) before sending to Gemini instead of just `head()`.
    *   Allowing Gemini to request specific aggregations or filters on fetched data.
*   **Visualization Generation:** Ask Gemini to suggest or even attempt to generate basic chart configurations (e.g., Vega-Lite specs) based on its analysis.
*   **Persistent Chat History (Optional):** Option to save/load chat sessions.
*   **Error Handling & Resilience:** Continue to improve robustness for diverse and complex PBIX/PBIT files.
*   **Cost Estimation/Token Counting Display (Advanced):** Provide users an idea of token usage for transparency.

---

**Happy Power BI Exploring with PBIXplorer! 📊**