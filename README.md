
# PBIT Metadata Chatbot & Explorer 🤖🔍

[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.20%2B-FF4B4B.svg)](https://streamlit.io)

A local, Streamlit-based application to analyze and explore the metadata of Power BI Template (.pbit) files. This tool allows users to upload a `.pbit` file and interact with its contents through both a chatbot interface and a structured metadata explorer.

**No cloud services are used, no Power BI Desktop installation is required to run this tool, and all processing happens locally.**

## Features ✨

*   **PBIT File Parsing:**
    *   Extracts metadata from `.pbit` files (which are ZIP archives).
    *   Handles various text encodings and BOMs for internal JSON files.
*   **Metadata Extraction:**
    *   **Data Model:** Tables, columns (with data types), DAX measures (with formulas), calculated columns (with formulas), and relationships.
    *   **M Queries (Power Query):** Extracts M scripts associated with tables and performs basic analysis to identify data sources and common transformation steps.
    *   **Report Structure:** Report pages, visuals on each page (type, title), and fields/measures used by each visual.
*   **Interactive Chatbot:**
    *   Ask natural language questions about the PBIT file's metadata. Examples:
        *   "List all tables"
        *   "Describe table 'Sales'"
        *   "What's the formula for measure 'Total Revenue'?"
        *   "List relationships for the 'Product' table"
        *   "Show me the M query for table 'SalesData'"
        *   "What visuals are on the 'Overview' page?"
        *   "Where is the 'CustomerID' column used?"
    *   Chat interface with auto-scrolling for new messages.
*   **Metadata Explorer:**
    *   Browse extracted metadata in a structured, searchable sidebar view:
        *   Tables & Columns
        *   Measures (with DAX)
        *   Calculated Columns (with DAX)
        *   Relationships
        *   M Queries (with script and basic analysis)
        *   Report Structure (Pages > Visuals > Fields)
    *   Search functionality within each explorer category.
*   **Local & Secure:** All file processing and analysis occur locally on your machine. No data is sent to external services.

## Demo Streamlit App 👨‍💻

You can test the app hosted at **https://pbit-chatbot.streamlit.app/**.

*(sample .pbit files can be found in the [templates](templates) folder of the repository)*

## Why this tool? 🤔

Understanding the structure and components of complex Power BI files can be challenging. This tool aims to simplify this by providing:

*   **Quick Insights:** Get an overview of a PBIT file without needing Power BI Desktop.
*   **Debugging Aid:** Help identify how tables are related, where measures are used, or what transformations are applied in Power Query.
*   **Documentation Assistance:** Extract definitions and structures for documentation purposes.
*   **Learning Tool:** Explore how Power BI reports are constructed.

## Tech Stack 🛠️

*   **Python 3.8+**
*   **Streamlit:** For the web application interface.
*   **Pandas:** For displaying tabular data in the explorer.
*   **Standard Python libraries:** `zipfile`, `json`, `os`, `re`, `codecs`.

## File Structure 📁

```
pbit-chatbot/
├── templates/               # Includes .pbit files for testing
├── .gitignore               # Git ignore
├── app.py                   # Main Streamlit application
├── chatbot_logic.py         # Module for query answering
├── pbit_parser.py           # Module to parse .pbit files & M queries
├── README.md                # This file
└── requirements.txt         # Python dependencies
```

## Setup & Installation 🚀

1.  **Clone the repository (or download the files):**
    ```bash
    git clone https://github.com/schromrvin/pbit-chatbot
    cd pbit-chatbot
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # Activate it:
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application ▶️

Once the setup is complete, run the Streamlit application from the `pbit-chatbot` directory:

```bash
streamlit run app.py
```

This will open the application in your default web browser (usually at `http://localhost:8501`).

## How to Use 📖

1.  **Launch the application** as described above.
2.  **Upload a `.pbit` file** using the file uploader in the sidebar.
3.  **Wait for processing:** The application will parse the file. A success or error message will appear in the sidebar.
4.  **Interact:**
    *   **Chatbot (Main Area):** Type your questions about the PBIT metadata into the chat input at the bottom.
    *   **Metadata Explorer (Sidebar):** Select a metadata category (e.g., "Tables & Columns", "M Queries") from the dropdown. Use the search box to filter the displayed items within that category. Expand items to see more details.

## Limitations & Future Work 🚧

*   **M Query Parsing Complexity:** The current M query analysis is basic (keyword/regex-based). Full M language parsing is extremely complex and out of scope for this version.
*   **Proprietary Format:** The `.pbit`/`.pbix` format is proprietary and internal structures can change with Power BI updates. The parser might need adjustments for files created with very new or very old Power BI Desktop versions if significant structural changes occur.
*   **No Data Querying:** This tool analyzes **metadata only**. It does not (and cannot without the Power BI engine) query or display the actual data stored within the PBIT file.
*   **Error Handling:** While efforts have been made, parsing diverse PBIT files can encounter unexpected structures. More robust error handling for edge cases could be added.

**Potential Future Enhancements:**

*   More advanced NLP for the chatbot (e.g., using NLTK/spaCy if installable, handling follow-up questions).
*   Deeper parsing of visual configurations in `Report/Layout`.
*   Support for directly analyzing certain `.pbix` structures (if they contain accessible JSON model definitions).
*   Visualizations of metadata (e.g., a graph for relationships).
*   Export functionality for extracted metadata (e.g., to CSV, JSON).

---

**Happy PBIT Exploring! 📊**