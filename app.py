import streamlit as st
import os
import tempfile
import pandas as pd # For displaying data in tables
from pbit_parser import parse_pbit_file
from chatbot_logic import process_query # We'll still keep the chat functionality

# --- Page Configuration ---
st.set_page_config(page_title="PBIT Metadata Explorer & Chatbot", layout="wide")

# --- Session State Initialization ---
if "pbit_metadata" not in st.session_state:
    st.session_state.pbit_metadata = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = None

# --- UI Elements ---
st.title("Power BI Template (.pbit) Explorer & Chatbot 🤖")

# --- File Upload and Processing ---
uploaded_file = st.sidebar.file_uploader("Choose a .pbit file", type=["pbit"])

if uploaded_file is not None:
    if st.session_state.uploaded_file_name != uploaded_file.name:
        st.session_state.chat_history = [] 
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.pbit_metadata = None # Reset metadata for new file
        
        with st.spinner(f"Processing '{uploaded_file.name}'..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pbit") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_file_path = tmp_file.name
            
            try:
                metadata = parse_pbit_file(temp_file_path)
                st.session_state.pbit_metadata = metadata
                if metadata:
                    st.sidebar.success(f"Parsed '{uploaded_file.name}'!")
                    # Initialize chat with a greeting if new file successfully parsed
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": f"Analyzed '{metadata.get('file_name', 'your file')}'. You can ask questions or explore its metadata below."}
                    )
                else:
                    st.sidebar.error("Could not parse the PBIT file.")
                    st.session_state.pbit_metadata = None
            except Exception as e:
                st.sidebar.error(f"Error processing: {e}")
                st.session_state.pbit_metadata = None
            finally:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
else:
    if not st.session_state.pbit_metadata: # Only show if no file is loaded yet
        st.info("👈 Upload a .pbit file using the sidebar to get started.")


# --- Main Application Layout (Chat and Explorer) ---
if st.session_state.pbit_metadata:
    metadata = st.session_state.pbit_metadata
    st.header(f"File: {metadata.get('file_name', 'N/A')}")

    # Create two columns for Chat and Explorer
    col_chat, col_explorer = st.columns([0.6, 0.4]) # Adjust ratio as needed

    # --- Column 1: Chatbot Interface ---
    with col_chat:
        st.subheader("💬 Chat with Metadata")
        
        # Display chat messages from history
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Accept user input
        if prompt := st.chat_input("Ask about the PBIT metadata..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = process_query(prompt, metadata)
                st.markdown(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})

    # --- Column 2: Interactive Metadata Explorer ---
    with col_explorer:
        st.subheader("🔍 Explore Metadata")

        explore_option = st.selectbox(
            "Choose metadata to explore:",
            ("Select an option...", "Tables & Columns", "Measures", "Calculated Columns", "Relationships", "M Queries", "Report Structure")
        )

        if explore_option == "Tables & Columns":
            st.markdown("#### Tables and Columns")
            if metadata.get("tables"):
                for table in sorted(metadata["tables"], key=lambda x: x.get("name", "")):
                    table_name = table.get("name", "Unknown Table")
                    with st.expander(f"Table: **{table_name}** ({len(table.get('columns',[]))} columns)"):
                        if table.get("columns"):
                            cols_data = [{"Column Name": col.get("name"), "Data Type": col.get("dataType")} for col in table["columns"]]
                            st.dataframe(pd.DataFrame(cols_data), use_container_width=True)
                        else:
                            st.write("No columns found for this table.")
            else:
                st.info("No table information found.")

        elif explore_option == "Measures":
            st.markdown("#### DAX Measures")
            if metadata.get("measures"):
                # Sort measures by name for consistent display
                sorted_measures = sorted(metadata["measures"].items())
                for measure_name, formula in sorted_measures:
                    with st.expander(f"Measure: **{measure_name}**"):
                        st.code(formula, language="dax")
            else:
                st.info("No DAX measures found.")

        elif explore_option == "Calculated Columns":
            st.markdown("#### Calculated Columns")
            if metadata.get("calculated_columns"):
                 # Sort calculated columns by name for consistent display
                sorted_cc = sorted(metadata["calculated_columns"].items())
                for cc_name, formula in sorted_cc: # cc_name is "Table.Column"
                    with st.expander(f"Calculated Column: **{cc_name}**"):
                        st.code(formula, language="dax")
            else:
                st.info("No calculated columns found.")
        
        elif explore_option == "Relationships":
            st.markdown("#### Relationships")
            if metadata.get("relationships"):
                rels_data = []
                for rel in metadata["relationships"]:
                    rels_data.append({
                        "From Table": rel.get("fromTable"),
                        "From Column": rel.get("fromColumn"),
                        "To Table": rel.get("toTable"),
                        "To Column": rel.get("toColumn"),
                        "Is Active": rel.get("isActive", True),
                        "Filter Direction": rel.get("crossFilteringBehavior", "N/A")
                    })
                st.dataframe(pd.DataFrame(rels_data), use_container_width=True)
            else:
                st.info("No relationships found.")

        elif explore_option == "M Queries":
            st.markdown("#### M (Power Query) Scripts")
            if metadata.get("m_queries"):
                for mq_info in sorted(metadata["m_queries"], key=lambda x: x.get("table_name", "")):
                    table_name = mq_info.get("table_name", "Unknown Table")
                    with st.expander(f"M Query for Table: **{table_name}**"):
                        analysis = mq_info.get("analysis", {})
                        st.markdown(f"**Sources:** {', '.join(analysis.get('sources', ['N/A']))}")
                        st.markdown(f"**Transformations:** {', '.join(analysis.get('transformations', ['N/A']))}")
                        st.markdown("**Script:**")
                        st.code(mq_info.get("script", "N/A"), language="powerquery") # or "m"
            else:
                st.info("No M Query information found.")

        elif explore_option == "Report Structure":
            st.markdown("#### Report Structure (Pages & Visuals)")
            if metadata.get("report_pages"):
                for page in sorted(metadata["report_pages"], key=lambda x: x.get("name", "")):
                    page_name = page.get("name", "Unknown Page")
                    with st.expander(f"Page: **{page_name}** ({len(page.get('visuals',[]))} visuals)"):
                        if page.get("visuals"):
                            for visual in page["visuals"]:
                                visual_title = visual.get('title') or visual.get('type', 'Unknown Visual')
                                st.markdown(f"##### Visual: {visual_title} (Type: {visual.get('type', 'N/A')})")
                                fields_used = visual.get("fields_used", [])
                                if fields_used:
                                    st.markdown("**Fields Used:**")
                                    for field in fields_used:
                                        st.markdown(f"- `{field}`")
                                else:
                                    st.markdown("_No specific fields identified for this visual._")
                                st.markdown("---")
                        else:
                            st.write("No visuals found on this page.")
            else:
                st.info("No report structure information found.")

        elif explore_option != "Select an option...":
             st.write(f"Exploration for '{explore_option}' coming soon!")

# --- Sidebar with Help/About (Optional) ---
st.sidebar.markdown("---")
st.sidebar.header("About & Help")
st.sidebar.info(
    "This app analyzes Power BI Template (.pbit) files. "
    "Upload a file to chat about its metadata or explore its structure."
)
st.sidebar.markdown("""
**Example Chat Questions:**
- List tables
- Describe table 'Sales'
- Formula for measure 'Total Sales'
- List relationships for 'Product'
- M Query for table 'SalesData'
- Visuals on page 'Overview'
- Where is column 'Product.Category' used?
""")