import streamlit as st
import os
import tempfile
import pandas as pd
from pbit_parser import parse_pbit_file 
from chatbot_logic import process_query 

# --- Page Configuration ---
st.set_page_config(page_title="PBIT Chatbot & Explorer", layout="wide")

# --- Session State Initialization ---
if "pbit_metadata" not in st.session_state:
    st.session_state.pbit_metadata = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = None
if "original_uploaded_file_name" not in st.session_state: # ADD THIS LINE
    st.session_state.original_uploaded_file_name = None
if "explorer_search_term" not in st.session_state: 
    st.session_state.explorer_search_term = ""
# Initialize explorer_option correctly
if "explorer_option" not in st.session_state: 
    st.session_state.explorer_option = "Select an option..."
if "run_id" not in st.session_state: # To help trigger JS execution for scrolling
    st.session_state.run_id = 0


# --- Helper function for filtering dictionary items (for explorer) ---
def filter_dict_items(items_dict, search_term):
    if not search_term: # If search term is empty, return all items
        return items_dict
    search_term_lower = search_term.lower()
    return {
        k: v for k, v in items_dict.items() 
        if search_term_lower in str(k).lower() or 
           (isinstance(v, str) and search_term_lower in v.lower()) # Check if v is string for direct search
           # Add more sophisticated searching within 'v' if v can be other types (e.g., lists, dicts)
    }

# --- Sidebar UI ---
st.sidebar.title("📊 PBIT Chatbot")
st.sidebar.markdown("---")

# --- File Upload in Sidebar ---
# Use a callback to reset dependent states when a new file is uploaded
def on_file_upload_change():
    if st.session_state.pbit_uploader is None and st.session_state.pbit_metadata is not None:
        st.session_state.pbit_metadata = None
        st.session_state.original_uploaded_file_name = None # ADD THIS RESET
        st.session_state.uploaded_file_name = None # You might already have this or similar
        st.session_state.chat_history = []
        st.session_state.explorer_option = "Select an option..."
        st.session_state.explorer_search_term = ""
    # This function is called when the file uploader's value changes.
    # If a new file is uploaded, uploaded_file will not be None.
    # If the file is removed, uploaded_file will be None.
    # We only want to reset things if a *new* file is effectively being processed.
    # The main logic block for uploaded_file handles the actual processing.
    # Here, we primarily ensure that if the uploader is cleared, we reset relevant states.
    if st.session_state.pbit_uploader is None and st.session_state.pbit_metadata is not None:
        st.session_state.pbit_metadata = None
        st.session_state.uploaded_file_name = None
        st.session_state.chat_history = []
        st.session_state.explorer_option = "Select an option..."
        st.session_state.explorer_search_term = ""
        # No st.rerun() here, let the main flow handle it or Streamlit's natural rerun.

uploaded_file = st.sidebar.file_uploader(
    "Choose a .pbit file", 
    type=["pbit"], 
    key="pbit_uploader",
    on_change=on_file_upload_change # Callback when file is uploaded or removed
)

if uploaded_file is not None:
    # Process if it's a new file name or if metadata is not loaded for the *original* file name
    if st.session_state.original_uploaded_file_name != uploaded_file.name or st.session_state.pbit_metadata is None: # MODIFIED condition slightly
        st.session_state.chat_history = [] 
        st.session_state.original_uploaded_file_name = uploaded_file.name # STORE ORIGINAL NAME
        st.session_state.pbit_metadata = None 
        
        with st.spinner(f"Processing '{uploaded_file.name}'..."): # USE ORIGINAL NAME in spinner
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pbit") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_file_path = tmp_file.name
            
            try:
                metadata = parse_pbit_file(temp_file_path) 
                st.session_state.pbit_metadata = metadata
                if metadata:
                    st.sidebar.success(f"Parsed '{st.session_state.original_uploaded_file_name}'!") # USE ORIGINAL NAME
                    st.session_state.chat_history = [
                        {"role": "assistant", "content": f"Analyzed '**{st.session_state.original_uploaded_file_name}**'. How can I help you today?"} # USE ORIGINAL NAME
                    ]
                    st.session_state.explorer_option = "Select an option..." 
                    st.session_state.explorer_search_term = ""
                    st.session_state.run_id += 1 
                else:
                    st.sidebar.error("Could not parse the PBIT file. Check console for parser warnings.")
                    st.session_state.pbit_metadata = None 
                    st.session_state.original_uploaded_file_name = None # RESET if parsing failed
            except Exception as e:
                st.sidebar.error(f"An error occurred during PBIT processing: {e}")
                st.session_state.pbit_metadata = None
                st.session_state.original_uploaded_file_name = None # RESET on exception
            finally:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path) 
                st.rerun() 
elif st.session_state.original_uploaded_file_name is not None and uploaded_file is None: # MODIFIED: check original_uploaded_file_name
    # This means the file uploader was cleared by the user
    if st.session_state.pbit_metadata is not None: 
        st.session_state.pbit_metadata = None
        st.session_state.original_uploaded_file_name = None # RESET original name
        st.session_state.chat_history = []
        st.session_state.explorer_option = "Select an option..."
        st.session_state.explorer_search_term = ""
        st.rerun()

# --- Interactive Metadata Explorer in Sidebar ---
if st.session_state.pbit_metadata:
    metadata_sb = st.session_state.pbit_metadata 
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Explore Metadata")
    
    EXPLORER_OPTIONS = ("Select an option...", "Tables & Columns", "Measures", "Calculated Columns", 
                        "Relationships", "M Queries", "Report Structure")

    # Callback for when the explorer option (selectbox) changes
    def on_explorer_option_change():
        # The selectbox value is automatically updated in st.session_state.explorer_option due to the key
        # We just need to reset the search term when the category changes.
        st.session_state.explorer_search_term = ""
        # No st.rerun() needed here, Streamlit handles rerun on widget value change with a key.

    st.sidebar.selectbox(
        "Choose metadata to explore:",
        options=EXPLORER_OPTIONS,
        key="explorer_option", # Session state key directly links to st.session_state.explorer_option
        on_change=on_explorer_option_change 
    )
    
    # Text input for searching within the explorer view
    # The value is directly bound to st.session_state.explorer_search_term via the key
    st.sidebar.text_input(
        "Search current explorer view:",
        key="explorer_search_term" # Session state key
        # No on_change needed here if filtering happens on each rerun based on this state.
        # If live-as-you-type filtering is desired and needs to force a rerun, an on_change could be added.
    )
    search_term_sb = st.session_state.explorer_search_term.lower() # Get current search term for filtering

    # --- Display logic based on st.session_state.explorer_option ---
    if st.session_state.explorer_option == "Tables & Columns":
        st.sidebar.markdown("##### Tables and Columns")
        all_tables = sorted(metadata_sb.get("tables", []), key=lambda x: x.get("name", ""))
        filtered_tables = [
            t for t in all_tables if not search_term_sb or 
            search_term_sb in t.get("name", "").lower() or 
            any(search_term_sb in col.get("name","").lower() or search_term_sb in col.get("dataType","").lower() for col in t.get("columns",[]))
        ] if metadata_sb.get("tables") else []
        
        if filtered_tables:
            for table in filtered_tables:
                table_name = table.get("name", "Unknown Table")
                with st.sidebar.expander(f"Table: **{table_name}** ({len(table.get('columns',[]))} columns)"):
                    if table.get("columns"):
                        cols_data = [{"Column Name": col.get("name"), "Data Type": col.get("dataType")} for col in table["columns"]]
                        st.dataframe(pd.DataFrame(cols_data), use_container_width=True, height=min(250, (len(cols_data) + 1) * 35 + 3))
                    else: st.write("No columns found for this table.")
        elif search_term_sb and metadata_sb.get("tables"): st.sidebar.info(f"No tables or columns match '{st.session_state.explorer_search_term}'.")
        elif not metadata_sb.get("tables"): st.sidebar.info("No table information found.")

    elif st.session_state.explorer_option == "Measures":
        st.sidebar.markdown("##### DAX Measures")
        all_measures = metadata_sb.get("measures", {})
        filtered_measures = filter_dict_items(all_measures, search_term_sb)
        if filtered_measures:
            for measure_name, formula in sorted(filtered_measures.items()):
                with st.sidebar.expander(f"Measure: **{measure_name}**"):
                    st.code(formula, language="dax")
        elif search_term_sb and all_measures : st.sidebar.info(f"No measures match '{st.session_state.explorer_search_term}'.")
        elif not all_measures : st.sidebar.info("No DAX measures found.")

    elif st.session_state.explorer_option == "Calculated Columns":
        st.sidebar.markdown("##### Calculated Columns")
        all_cc = metadata_sb.get("calculated_columns", {})
        filtered_cc = filter_dict_items(all_cc, search_term_sb)
        if filtered_cc:
            for cc_name, formula in sorted(filtered_cc.items()):
                with st.sidebar.expander(f"Calculated Column: **{cc_name}**"):
                    st.code(formula, language="dax")
        elif search_term_sb and all_cc : st.sidebar.info(f"No calculated columns match '{st.session_state.explorer_search_term}'.")
        elif not all_cc : st.sidebar.info("No calculated columns found.")
    
    elif st.session_state.explorer_option == "Relationships":
        st.sidebar.markdown("##### Relationships")
        all_rels = metadata_sb.get("relationships", [])
        if not all_rels:
            st.sidebar.info("No relationships found.")
        else:
            filtered_rels = [
                r for r in all_rels if not search_term_sb or 
                search_term_sb in str(r.get("fromTable","")).lower() or 
                search_term_sb in str(r.get("toTable","")).lower() or 
                search_term_sb in str(r.get("fromColumn","")).lower() or 
                search_term_sb in str(r.get("toColumn","")).lower()
            ]
            if filtered_rels:
                rels_data = [{"From": f"{r.get('fromTable','?')}.{r.get('fromColumn','?')}",
                              "To": f"{r.get('toTable','?')}.{r.get('toColumn','?')}",
                              "Active": r.get("isActive", True), 
                              "Filter Dir.": r.get("crossFilteringBehavior", "N/A")}
                             for r in filtered_rels]
                df_rels = pd.DataFrame(rels_data)
                st.sidebar.dataframe(df_rels, use_container_width=True, height=min(300, (len(df_rels) + 1) * 35 + 3))
            elif search_term_sb:
                st.sidebar.info(f"No relationships match '{st.session_state.explorer_search_term}'.")

    elif st.session_state.explorer_option == "M Queries":
        st.sidebar.markdown("##### M (Power Query) Scripts")
        all_m_queries = sorted(metadata_sb.get("m_queries", []), key=lambda x: x.get("table_name", ""))
        filtered_m_queries = [
            mq for mq in all_m_queries if not search_term_sb or 
            search_term_sb in mq.get("table_name","").lower() or 
            search_term_sb in mq.get("script","").lower() or
            any(search_term_sb in s.lower() for s in mq.get("analysis",{}).get("sources",[])) or
            any(search_term_sb in t.lower() for t in mq.get("analysis",{}).get("transformations",[]))
        ]
        if filtered_m_queries:
            for mq_info in filtered_m_queries:
                with st.sidebar.expander(f"M Query for Table: **{mq_info.get('table_name', '?')}**"):
                    analysis = mq_info.get("analysis", {})
                    st.markdown(f"**Identified Sources:** {', '.join(analysis.get('sources', ['N/A']))}")
                    st.markdown(f"**Common Transformations:** {', '.join(analysis.get('transformations', ['N/A']))}")
                    st.markdown("**Script:**")
                    st.code(mq_info.get("script", "N/A"), language="powerquery")
        elif search_term_sb and metadata_sb.get("m_queries"): st.sidebar.info(f"No M Queries match '{st.session_state.explorer_search_term}'.")
        elif not metadata_sb.get("m_queries"): st.sidebar.info("No M Query information found.")

    elif st.session_state.explorer_option == "Report Structure":
        st.sidebar.markdown("##### Report Structure (Pages & Visuals)")
        all_pages = sorted(metadata_sb.get("report_pages", []), key=lambda x: x.get("name", ""))
        filtered_pages = [
            p for p in all_pages if not search_term_sb or
            search_term_sb in p.get("name","").lower() or
            any(search_term_sb in str(v.get("title","")).lower() or
                search_term_sb in str(v.get("type","")).lower() or
                any(search_term_sb in f.lower() for f in v.get("fields_used",[])) 
                for v in p.get("visuals",[]))
        ]
        if filtered_pages:
            for page in filtered_pages:
                page_name = page.get("name", "Unknown Page")
                with st.sidebar.expander(f"Page: **{page_name}** ({len(page.get('visuals',[]))} visuals)"):
                    if page.get("visuals"):
                        for visual in page["visuals"]:
                            # --- REVERTED FORMATTING HERE ---
                            visual_title_or_type = visual.get('title') if visual.get('title') else visual.get('type', 'Unknown Visual')
                            st.markdown(f"**{visual_title_or_type}** (Type: {visual.get('type', 'N/A')})")
                            fields = visual.get("fields_used", [])
                            if fields:
                                # Using st.caption for a more compact display of fields
                                st.caption(f"Fields: {', '.join(f'`{f}`' for f in fields)}")
                            else:
                                st.caption("_No specific fields identified._")
                            # Removed the extra "---" for a slightly cleaner look between visuals, optional
                            # st.markdown("---") 
                            # --- END OF REVERTED FORMATTING ---
                    else:
                        st.write("No visuals found on this page.")
        elif search_term_sb and metadata_sb.get("report_pages"): st.sidebar.info(f"No report items match '{st.session_state.explorer_search_term}'.")
        elif not metadata_sb.get("report_pages"): st.sidebar.info("No report structure information found.")

# --- Main Page: Chatbot Interface ---
st.header("📊 PBIT Chatbot")

if not st.session_state.pbit_metadata:
    st.info("👈 Upload a .pbit file using the sidebar to analyze and chat about its metadata.")
else:
    # Use the original uploaded filename for display
    display_filename = st.session_state.get("original_uploaded_file_name", "N/A") # NEW LINE
    st.caption(f"Currently analyzing: **{display_filename}**") # MODIFIED LINE

    # Apply max-height for the chat container
    chat_box_style = (
        "max-height: 500px; "  # Or your preferred max scrollable height
        "overflow-y: auto; "
        "padding: 10px; "
        "border-radius: 5px; "
        "margin-bottom: 10px;"
        # Optional: Add a min-height if you want the box to have some presence even when empty
        # "min-height: 100px;" 
    )
    st.markdown(f'<div id="chat-messages-container" style="{chat_box_style}">', unsafe_allow_html=True)
    
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"]) # Display the message content
    
    st.markdown('</div>', unsafe_allow_html=True) # Close the chat messages container div

    # JavaScript for auto-scrolling, keyed to run_id to force re-execution
    js_key_for_html_component = f"auto_scroll_js_{st.session_state.run_id}"
    js_autoscroll = f"""
    <script name="{js_key_for_html_component}"> // Add a name for debugging
        // console.log("Auto-scroll script '{js_key_for_html_component}' attempting to execute...");
        setTimeout(function() {{
            var chatContainer = document.getElementById("chat-messages-container");
            if (chatContainer) {{
                // console.log("Found chat-messages-container, scrolling to bottom:", chatContainer.scrollHeight);
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }} else {{
                // console.log("chat-messages-container NOT found by script '{js_key_for_html_component}'.");
            }}
        }}, 150); // Delay to allow DOM update
    </script>
    """
    # Use st.components.v1.html for more reliable JS execution
    if st.session_state.chat_history: # Only inject if there are messages
        st.components.v1.html(js_autoscroll, height=0, scrolling=False)

    # Chat input
    if prompt := st.chat_input("Ask about the PBIT metadata..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        with st.spinner("Thinking..."):
            response = process_query(prompt, st.session_state.pbit_metadata)
        
        st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.session_state.run_id += 1 # Increment to ensure JS runs again
        st.rerun() # Rerun to display new messages and trigger scroll

st.sidebar.markdown("---")
st.sidebar.caption("PBIT Chatbot - Developed by Marvin Heng")