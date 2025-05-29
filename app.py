import streamlit as st
import os
import tempfile
import pandas as pd
import zipfile
from pbit_parser import parse_pbit_file, extract_report_layout_from_zip
# Now import the Gemini-specific functions from chatbot_logic
from chatbot_logic import configure_gemini_model, process_query_with_gemini

# --- Page Configuration ---
st.set_page_config(page_title="PBIXpert Chatbot & Explorer", layout="wide") # Renamed

# --- Session State Initialization ---
if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = ""
if "gemini_configured" not in st.session_state:
    st.session_state.gemini_configured = False
if "pbit_metadata" not in st.session_state:
    st.session_state.pbit_metadata = None
if "pbix_object" not in st.session_state:
    st.session_state.pbix_object = None
if "pbix_report_layout" not in st.session_state:
    st.session_state.pbix_report_layout = None
if "active_file_type" not in st.session_state:
    st.session_state.active_file_type = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_file_name" not in st.session_state: # Key for file_uploader widget
    st.session_state.uploaded_file_name = None
if "original_uploaded_file_name" not in st.session_state: # Stored name of successfully parsed file
    st.session_state.original_uploaded_file_name = None
if "explorer_search_term" not in st.session_state:
    st.session_state.explorer_search_term = ""
if "explorer_option" not in st.session_state:
    st.session_state.explorer_option = "Select an option..."
if "run_id" not in st.session_state: # For JS scroll
    st.session_state.run_id = 0
if "sidebar_pbix_table_select_viewer" not in st.session_state: # For PBIX table data selection in sidebar
    st.session_state.sidebar_pbix_table_select_viewer = "Select a table..."


# --- Helper function for filtering dictionary items (for PBIT explorer) ---
def filter_dict_items(items_dict, search_term):
    # ... (same as before) ...
    if not search_term: return items_dict
    search_term_lower = search_term.lower()
    return {
        k: v for k, v in items_dict.items()
        if search_term_lower in str(k).lower() or
           (isinstance(v, str) and search_term_lower in v.lower())
    }

# --- Sidebar UI ---
st.sidebar.title("📊 PBIXpert Analyzer") # Renamed
st.sidebar.markdown("---")

# Gemini API Key Input
st.sidebar.subheader("Gemini API Configuration")
api_key_input = st.sidebar.text_input(
    "Enter your Gemini API Key",
    type="password",
    key="gemini_api_key_input", # Use a different key from session_state.gemini_api_key if needed for on_change
    value=st.session_state.gemini_api_key
)

if api_key_input and api_key_input != st.session_state.gemini_api_key:
    st.session_state.gemini_api_key = api_key_input
    st.session_state.gemini_configured = False # Force reconfigure

if st.session_state.gemini_api_key and not st.session_state.gemini_configured:
    with st.spinner("Configuring Gemini Model..."):
        config_success = configure_gemini_model(st.session_state.gemini_api_key)
        if config_success:
            st.session_state.gemini_configured = True
            st.sidebar.success("Gemini model configured!")
            st.rerun() # Rerun to reflect change and potentially clear spinner if it was quick
        else:
            st.sidebar.error("Failed to configure Gemini. Check API key and console.")
            st.session_state.gemini_configured = False
elif not st.session_state.gemini_api_key:
    st.sidebar.warning("Please enter your Gemini API Key to enable the chatbot.")
    st.session_state.gemini_configured = False


st.sidebar.markdown("---")
st.sidebar.subheader("File Upload")

# --- File Upload in Sidebar ---
def on_file_upload_change():
    # ... (same as before, ensure all relevant states are reset) ...
    if st.session_state.get("pbit_uploader_widget") is None: # Check the widget's key
        if st.session_state.active_file_type is not None:
            st.session_state.pbit_metadata = None
            st.session_state.pbix_object = None
            st.session_state.pbix_report_layout = None
            st.session_state.active_file_type = None
            st.session_state.original_uploaded_file_name = None
            st.session_state.chat_history = [] # Clear chat when file is removed
            st.session_state.explorer_option = "Select an option..."
            st.session_state.explorer_search_term = ""
            st.session_state.sidebar_pbix_table_select_viewer = "Select a table..."
            st.session_state.run_id += 1
            # st.rerun() # Let main flow handle rerun

uploaded_file = st.sidebar.file_uploader(
    "Choose a .pbit or .pbix file",
    type=["pbit", "pbix"],
    key="pbit_uploader_widget", # Use a distinct key for the widget itself
    on_change=on_file_upload_change
)

# Processing logic for uploaded_file
if uploaded_file is not None:
    # If it's a new file OR if the current original_uploaded_file_name doesn't match (meaning a different file was uploaded)
    if st.session_state.original_uploaded_file_name != uploaded_file.name or not st.session_state.active_file_type:
        # This is a new file upload or re-upload of a different file
        st.session_state.chat_history = [
             {"role": "assistant", "content": f"Processing '{uploaded_file.name}'..."} # Initial message
        ] if st.session_state.gemini_configured else [
             {"role": "assistant", "content": f"Processing '{uploaded_file.name}'. Note: Gemini not configured."}
        ]
        st.session_state.original_uploaded_file_name = uploaded_file.name # Set early
        st.session_state.pbit_metadata = None
        st.session_state.pbix_object = None
        st.session_state.pbix_report_layout = None
        st.session_state.active_file_type = None # Will be set after successful parsing
        st.session_state.explorer_option = "Select an option..."
        st.session_state.explorer_search_term = ""
        st.session_state.sidebar_pbix_table_select_viewer = "Select a table..."
        st.session_state.run_id += 1

        with st.spinner(f"Analyzing '{uploaded_file.name}'... This may take a moment."):
            file_extension = os.path.splitext(uploaded_file.name)[1]
            # Create a temporary file with the correct extension
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_file_path = tmp_file.name

            report_layout_info_msg = ""
            initial_bot_message = f"Okay, I've analyzed **{uploaded_file.name}**. How can I help you with it?"

            try:
                if uploaded_file.name.endswith(".pbit"):
                    st.session_state.active_file_type = "pbit"
                    metadata = parse_pbit_file(temp_file_path)
                    st.session_state.pbit_metadata = metadata
                    if not metadata:
                        initial_bot_message = f"Could not fully parse PBIT file '{uploaded_file.name}'. Some information might be missing."
                        st.sidebar.error(f"PBIT parsing failed for {uploaded_file.name}.")
                        st.session_state.active_file_type = None # Parsing failed
                    else:
                        st.sidebar.success(f"PBIT '{uploaded_file.name}' parsed!")

                elif uploaded_file.name.endswith(".pbix"):
                    from pbixray_lib.core import PBIXRay # Import here
                    st.session_state.active_file_type = "pbix"
                    pbix_obj = PBIXRay(temp_file_path)
                    st.session_state.pbix_object = pbix_obj

                    try: # Attempt to parse Report/Layout from PBIX
                        with zipfile.ZipFile(temp_file_path, 'r') as pbix_zip_for_layout:
                            report_layout_data = extract_report_layout_from_zip(pbix_zip_for_layout)
                            if report_layout_data:
                                st.session_state.pbix_report_layout = report_layout_data
                                report_layout_info_msg = " Report layout was also parsed."
                            else:
                                report_layout_info_msg = " Report layout not found or could not be parsed from this PBIX."
                    except Exception: # Silently fail on report layout for PBIX for now
                        report_layout_info_msg = " Note: Could not parse report layout from PBIX."
                        st.session_state.pbix_report_layout = None
                    
                    initial_bot_message = f"Okay, I've analyzed PBIX file **{uploaded_file.name}**. {report_layout_info_msg} What can I help you analyze?"
                    st.sidebar.success(f"PBIX '{uploaded_file.name}' parsed!{report_layout_info_msg}")

                else: # Should not happen
                    initial_bot_message = f"Unsupported file type: {uploaded_file.name}."
                    st.sidebar.error(f"Unsupported file type: {uploaded_file.name}")
                    st.session_state.active_file_type = None

            except Exception as e:
                initial_bot_message = f"An error occurred during processing of '{uploaded_file.name}': {e}"
                st.sidebar.error(f"Processing error: {e}")
                st.session_state.pbit_metadata = None; st.session_state.pbix_object = None
                st.session_state.pbix_report_layout = None; st.session_state.active_file_type = None
                st.session_state.original_uploaded_file_name = None # Reset if processing failed entirely
            finally:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            
            # Update chat history after processing
            if st.session_state.active_file_type: # Only if parsing was somewhat successful
                 st.session_state.chat_history = [{"role": "assistant", "content": initial_bot_message}]
            else: # Parsing failed
                 st.session_state.chat_history = [{"role": "assistant", "content": f"Failed to process '{uploaded_file.name}'. Please try another file."}]
            st.rerun()

# This handles the case where the file is REMOVED from the uploader
elif st.session_state.original_uploaded_file_name is not None and uploaded_file is None:
    # on_file_upload_change should have handled resets. This rerun ensures UI updates.
    if st.session_state.active_file_type is not None : # If something was active, and now it's gone
        st.rerun()


# --- Interactive Metadata Explorer in Sidebar ---
# (This section remains largely the same as in the previous response, with corrected PBIXRay attribute access)
if st.session_state.active_file_type:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Explore Metadata")

    EXPLORER_OPTIONS_BASE = ("Select an option...", "Tables & Columns", "Measures", "Calculated Columns",
                               "Relationships", "M Queries", "Report Structure")
    EXPLORER_OPTIONS_PBIX_EXTRA = ("View Table Data (Sidebar)",)

    if st.session_state.active_file_type == "pbit":
        EXPLORER_OPTIONS = EXPLORER_OPTIONS_BASE
    elif st.session_state.active_file_type == "pbix":
        EXPLORER_OPTIONS = EXPLORER_OPTIONS_BASE + EXPLORER_OPTIONS_PBIX_EXTRA
    else:
        EXPLORER_OPTIONS = ("Select an option...",)

    def on_explorer_option_change_sb():
        st.session_state.explorer_search_term = ""
        if st.session_state.explorer_option != "View Table Data (Sidebar)":
            st.session_state.sidebar_pbix_table_select_viewer = "Select a table..."

    st.sidebar.selectbox(
        "Choose metadata to explore:",
        options=EXPLORER_OPTIONS,
        key="explorer_option",
        on_change=on_explorer_option_change_sb
    )

    if st.session_state.explorer_option != "View Table Data (Sidebar)":
        st.sidebar.text_input(
            "Search current explorer view:",
            key="explorer_search_term"
        )
    search_term_sb = st.session_state.explorer_search_term.lower()

    if st.session_state.explorer_option == "Tables & Columns":
        st.sidebar.markdown("##### Tables and Columns")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            metadata_sb_pbit = st.session_state.pbit_metadata
            all_tables = sorted(metadata_sb_pbit.get("tables", []), key=lambda x: x.get("name", ""))
            filtered_tables = [
                t for t in all_tables if not search_term_sb or
                search_term_sb in t.get("name", "").lower() or
                any(search_term_sb in col.get("name","").lower() or search_term_sb in col.get("dataType","").lower() for col in t.get("columns",[]))
            ] if metadata_sb_pbit.get("tables") else []

            if filtered_tables:
                for table in filtered_tables:
                    table_name = table.get("name", "Unknown Table")
                    with st.sidebar.expander(f"Table: **{table_name}** ({len(table.get('columns',[]))} columns)"):
                        if table.get("columns"):
                            cols_data = [{"Column Name": col.get("name"), "Data Type": col.get("dataType")} for col in table["columns"]]
                            st.dataframe(pd.DataFrame(cols_data), use_container_width=True, height=min(250, (len(cols_data) + 1) * 35 + 3))
                        else: st.write("No columns found for this table.")
            elif search_term_sb and metadata_sb_pbit.get("tables"): st.sidebar.info(f"No tables or columns match '{st.session_state.explorer_search_term}'.")
            elif not metadata_sb_pbit.get("tables"): st.sidebar.info("No table information found.")

        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_md = st.session_state.pbix_object
            all_table_names_pbix = sorted(list(pbix_md.tables))
            schema_df = pbix_md.schema # Access property

            filtered_table_names = [
                name for name in all_table_names_pbix if not search_term_sb or
                search_term_sb in name.lower() or
                any(
                    (search_term_sb in col_info['ColumnName'].lower() or search_term_sb in col_info['PandasDataType'].lower())
                    for _, col_info in schema_df[schema_df['TableName'] == name].iterrows()
                )
            ]
            if filtered_table_names:
                for table_name in filtered_table_names:
                    table_columns_df = schema_df[schema_df['TableName'] == table_name]
                    with st.sidebar.expander(f"Table: **{table_name}** ({len(table_columns_df)} columns)"):
                        if not table_columns_df.empty:
                            cols_data = [{"Column Name": row["ColumnName"], "Data Type": row["PandasDataType"]}
                                         for _, row in table_columns_df.iterrows()]
                            st.dataframe(pd.DataFrame(cols_data), use_container_width=True, height=min(250, (len(cols_data) + 1) * 35 + 3))
                        else: st.write("No columns found for this table.")
            elif search_term_sb and all_table_names_pbix: st.sidebar.info(f"No PBIX tables or columns match '{st.session_state.explorer_search_term}'.")
            elif not all_table_names_pbix: st.sidebar.info("No table information found in PBIX.")

    elif st.session_state.explorer_option == "Measures":
        st.sidebar.markdown("##### DAX Measures")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            metadata_sb_pbit = st.session_state.pbit_metadata
            all_measures = metadata_sb_pbit.get("measures", {})
            filtered_measures = filter_dict_items(all_measures, search_term_sb)
            if filtered_measures:
                for measure_name, formula in sorted(filtered_measures.items()):
                    with st.sidebar.expander(f"Measure: **{measure_name}**"):
                        st.code(formula, language="dax")
            elif search_term_sb and all_measures : st.sidebar.info(f"No measures match '{st.session_state.explorer_search_term}'.")
            elif not all_measures : st.sidebar.info("No DAX measures found.")

        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_md = st.session_state.pbix_object
            dax_measures_df = pbix_md.dax_measures # Property
            if dax_measures_df is not None and not dax_measures_df.empty:
                filtered_measures_df = dax_measures_df[
                    dax_measures_df.apply(lambda row: search_term_sb in f"{row['TableName']}.{row['Name']}".lower() or \
                                                      search_term_sb in str(row['Expression']).lower() or \
                                                      search_term_sb in str(row['DisplayFolder']).lower(), axis=1)
                ] if search_term_sb else dax_measures_df

                if not filtered_measures_df.empty:
                    for _, row in filtered_measures_df.sort_values(by=['TableName', 'Name']).iterrows():
                        measure_qual_name = f"{row['TableName']}.{row['Name']}"
                        with st.sidebar.expander(f"Measure: **{measure_qual_name}**"):
                            if pd.notna(row['DisplayFolder']): st.caption(f"Display Folder: {row['DisplayFolder']}")
                            if pd.notna(row['Description']): st.caption(f"Description: {row['Description']}")
                            st.code(row['Expression'], language="dax")
                elif search_term_sb: st.sidebar.info(f"No PBIX measures match '{st.session_state.explorer_search_term}'.")
            else: st.sidebar.info("No DAX measures found in PBIX.")

    elif st.session_state.explorer_option == "Calculated Columns":
        st.sidebar.markdown("##### Calculated Columns")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            pbit_meta = st.session_state.pbit_metadata
            all_cc = pbit_meta.get("calculated_columns", {})
            filtered_cc = filter_dict_items(all_cc, search_term_sb)
            if filtered_cc:
                for cc_name, formula in sorted(filtered_cc.items()):
                    with st.sidebar.expander(f"Calculated Column: **{cc_name}**"):
                        st.code(formula, language="dax")
            elif search_term_sb and all_cc : st.sidebar.info(f"No PBIT calculated columns match '{st.session_state.explorer_search_term}'.")
            elif not all_cc : st.sidebar.info("No PBIT calculated columns found.")

        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_obj = st.session_state.pbix_object
            dax_columns_df = pbix_obj.dax_columns # Property
            if dax_columns_df is not None and not dax_columns_df.empty:
                filtered_cc_df = dax_columns_df[
                    dax_columns_df.apply(lambda row: search_term_sb in f"{row['TableName']}.{row['ColumnName']}".lower() or \
                                                       search_term_sb in str(row['Expression']).lower(), axis=1)
                ] if search_term_sb else dax_columns_df

                if not filtered_cc_df.empty:
                    for _, row in filtered_cc_df.sort_values(by=['TableName', 'ColumnName']).iterrows():
                        cc_qual_name = f"{row['TableName']}.{row['ColumnName']}"
                        with st.sidebar.expander(f"Calculated Column: **{cc_qual_name}**"):
                            st.code(row['Expression'], language="dax")
                elif search_term_sb: st.sidebar.info(f"No PBIX calculated columns match '{st.session_state.explorer_search_term}'.")
            else: st.sidebar.info("No calculated columns found in PBIX.")

    # ... M Queries, Relationships, Report Structure (same as previous, ensure correct property access for PBIXRay) ...
    elif st.session_state.explorer_option == "M Queries" or st.session_state.explorer_option == "M Queries (Power Query)":
        st.sidebar.markdown("##### M (Power Query) Scripts")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            metadata_sb_pbit = st.session_state.pbit_metadata
            all_m_queries = sorted(metadata_sb_pbit.get("m_queries", []), key=lambda x: x.get("table_name", ""))
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
            elif search_term_sb and metadata_sb_pbit.get("m_queries"): st.sidebar.info(f"No M Queries match '{st.session_state.explorer_search_term}'.")
            elif not metadata_sb_pbit.get("m_queries"): st.sidebar.info("No M Query information found.")

        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_md = st.session_state.pbix_object
            power_query_df = pbix_md.power_query # Property
            if power_query_df is not None and not power_query_df.empty:
                filtered_pq_df = power_query_df[
                    power_query_df.apply(lambda row: search_term_sb in str(row['TableName']).lower() or \
                                                       search_term_sb in str(row['Expression']).lower(), axis=1)
                ] if search_term_sb else power_query_df

                if not filtered_pq_df.empty:
                    for _, row in filtered_pq_df.sort_values(by='TableName').iterrows():
                        with st.sidebar.expander(f"M Query for Table: **{row['TableName']}**"):
                            st.code(row['Expression'], language="powerquery")
                elif search_term_sb: st.sidebar.info(f"No PBIX M Queries match '{st.session_state.explorer_search_term}'.")
            else: st.sidebar.info("No M Query information found in PBIX.")

    elif st.session_state.explorer_option == "Relationships":
        st.sidebar.markdown("##### Relationships")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            metadata_sb_pbit = st.session_state.pbit_metadata
            all_rels = metadata_sb_pbit.get("relationships", [])
            if not all_rels: st.sidebar.info("No relationships found.")
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
        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_md = st.session_state.pbix_object
            relationships_df = pbix_md.relationships # Property
            if relationships_df is not None and not relationships_df.empty:
                filtered_rels_df = relationships_df[
                    relationships_df.apply(lambda row: search_term_sb in str(row['FromTableName']).lower() or \
                                                       search_term_sb in str(row['FromColumnName']).lower() or \
                                                       search_term_sb in str(row['ToTableName']).lower() or \
                                                       search_term_sb in str(row['ToColumnName']).lower(), axis=1)
                ] if search_term_sb else relationships_df

                if not filtered_rels_df.empty:
                    rels_data_pbix = []
                    for _, r_item in filtered_rels_df.iterrows(): # Changed variable name to avoid conflict
                        rels_data_pbix.append({
                            "From": f"{r_item.get('FromTableName','?')}.{r_item.get('FromColumnName','?')}",
                            "To": f"{r_item.get('ToTableName','?')}.{r_item.get('ToColumnName','?')}",
                            "Active": r_item.get("IsActive", True),
                            "Cardinality": r_item.get("Cardinality", "N/A"),
                            "Filter Dir.": r_item.get("CrossFilteringBehavior", "N/A")
                        })
                    df_rels_pbix = pd.DataFrame(rels_data_pbix)
                    st.sidebar.dataframe(df_rels_pbix, use_container_width=True, height=min(300, (len(df_rels_pbix) + 1) * 35 + 3))
                elif search_term_sb: st.sidebar.info(f"No PBIX relationships match '{st.session_state.explorer_search_term}'.")
            else: st.sidebar.info("No relationships found in PBIX.")

    elif st.session_state.explorer_option == "Report Structure":
        st.sidebar.markdown("##### Report Structure (Pages & Visuals)")
        report_pages_data = None
        source_type_for_msg = ""

        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            report_pages_data = st.session_state.pbit_metadata.get("report_pages", [])
            source_type_for_msg = "PBIT"
        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_report_layout:
            report_pages_data = st.session_state.pbix_report_layout
            source_type_for_msg = "PBIX"

        if report_pages_data:
            all_pages = sorted(report_pages_data, key=lambda x: x.get("name", "Unnamed Page"))
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
                                visual_title_or_type = visual.get('title') if visual.get('title') else visual.get('type', 'Unknown Visual')
                                st.markdown(f"**{visual_title_or_type}** (Type: {visual.get('type', 'N/A')})")
                                fields = visual.get("fields_used", [])
                                if fields: st.caption(f"Fields: {', '.join(f'`{f}`' for f in fields)}")
                                else: st.caption("_No specific fields identified._")
                        else: st.write("No visuals found on this page.")
            elif search_term_sb: st.sidebar.info(f"No report items match '{st.session_state.explorer_search_term}' in {source_type_for_msg}.")
        elif st.session_state.active_file_type == "pbix" and not st.session_state.pbix_report_layout:
            st.sidebar.info("Report structure (Report/Layout) was not found or parsed from this PBIX file.")
        else:
            st.sidebar.info(f"No report structure information found in {source_type_for_msg}.")


    elif st.session_state.explorer_option == "View Table Data (Sidebar)":
        if st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            st.sidebar.markdown("##### View Table Data (PBIX)")
            pbix_obj_for_view = st.session_state.pbix_object
            pbix_tables_for_view = sorted(list(pbix_obj_for_view.tables))

            if pbix_tables_for_view:
                table_options = ["Select a table..."] + pbix_tables_for_view
                selected_table_in_sb = st.sidebar.selectbox(
                    "Select table to view:",
                    options=table_options,
                    key="sidebar_pbix_table_select_viewer"
                )
                if selected_table_in_sb != "Select a table...":
                    try:
                        with st.spinner(f"Loading data for '{selected_table_in_sb}' in sidebar..."):
                            data_df_sb = pbix_obj_for_view.get_table(selected_table_in_sb)
                            st.sidebar.caption(f"Displaying preview of **{selected_table_in_sb}** ({len(data_df_sb)} rows):")
                            st.sidebar.dataframe(data_df_sb, height=300)
                    except Exception as e_sb_table:
                        st.sidebar.error(f"Could not load data for '{selected_table_in_sb}': {e_sb_table}")
            else:
                st.sidebar.info("No tables found in the PBIX file to view.")
        else:
            st.sidebar.info("This option is for PBIX files only.")


# --- Main Page: Chatbot Interface ---
st.header("📊 PBIXpert Chatbot & Explorer")

if not st.session_state.active_file_type:
    st.info("👈 Upload a .pbit or .pbix file and configure Gemini API Key in the sidebar to begin.")
elif not st.session_state.gemini_configured:
    st.info("👈 Please configure your Gemini API Key in the sidebar to enable the PBIXpert chatbot.")
else: # File is loaded AND Gemini is configured
    display_filename = st.session_state.get("original_uploaded_file_name", "N/A")
    file_type_display = st.session_state.active_file_type.upper() if st.session_state.active_file_type else ""
    st.caption(f"Currently analyzing {file_type_display}: **{display_filename}** with PBIXpert (Gemini).")

    # Chat history display
    chat_box_style = (
        "max-height: 600px; overflow-y: auto; padding: 10px; "
        "border-radius: 5px; margin-bottom: 10px;"
    )
    st.markdown(f'<div id="chat-messages-container" style="{chat_box_style}">', unsafe_allow_html=True)
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"]) # Gemini output is Markdown
    st.markdown('</div>', unsafe_allow_html=True)

    # Auto-scroll JS
    js_key_for_html_component = f"auto_scroll_js_{st.session_state.run_id}"
    js_autoscroll = f"""
    <script name="{js_key_for_html_component}">
        setTimeout(function() {{
            var chatContainer = document.getElementById("chat-messages-container");
            if (chatContainer) {{ chatContainer.scrollTop = chatContainer.scrollHeight; }}
        }}, 150);
    </script>
    """
    if st.session_state.chat_history:
        st.components.v1.html(js_autoscroll, height=0, scrolling=False)

    # Chat input
    if prompt := st.chat_input("Ask PBIXpert about the file or data concepts..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        response_text = "Error: Could not determine how to process query."
        with st.spinner("PBIXpert is thinking..."):
            current_file_data = None
            if st.session_state.active_file_type == "pbit":
                current_file_data = st.session_state.pbit_metadata
            elif st.session_state.active_file_type == "pbix":
                current_file_data = st.session_state.pbix_object
            
            if current_file_data and st.session_state.original_uploaded_file_name:
                response_text = process_query_with_gemini(
                    user_query=prompt,
                    primary_metadata=current_file_data,
                    file_type=st.session_state.active_file_type,
                    original_file_name=st.session_state.original_uploaded_file_name,
                    pbix_report_layout=st.session_state.pbix_report_layout if st.session_state.active_file_type == "pbix" else None
                )
            else:
                response_text = "It seems no file is loaded or an internal error occurred. Please try re-uploading."

        st.session_state.chat_history.append({"role": "assistant", "content": response_text})
        st.session_state.run_id += 1
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("PBIXpert Analyzer - Powered by Gemini")