import streamlit as st
import os
import tempfile
import pandas as pd
import zipfile
import json
import re
from pbit_parser import parse_pbit_file, extract_report_layout_from_zip
from chatbot_logic import (
    configure_gemini_model,
    format_metadata_for_gemini,
    generate_gemini_response,
    construct_initial_prompt,
    construct_reprompt_with_fetched_data,
    format_chat_history_for_prompt,
    MAX_TOOL_FETCHED_ROWS_FOR_REPROMPT,
    MAX_CHAT_HISTORY_TURNS
)

# --- Page Configuration ---
st.set_page_config(page_title="PBIXplorer Analysis Tool", layout="wide")

# --- Session State Initialization ---
if "gemini_api_key" not in st.session_state: st.session_state.gemini_api_key = ""
if "gemini_configured" not in st.session_state: st.session_state.gemini_configured = False
if "pbit_metadata" not in st.session_state: st.session_state.pbit_metadata = None
if "pbix_object" not in st.session_state: st.session_state.pbix_object = None
if "pbix_report_layout" not in st.session_state: st.session_state.pbix_report_layout = None
if "active_file_type" not in st.session_state: st.session_state.active_file_type = None
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "uploaded_file_widget" not in st.session_state: st.session_state.uploaded_file_widget = None # Key for file_uploader widget
if "original_uploaded_file_name" not in st.session_state: st.session_state.original_uploaded_file_name = None
if "explorer_search_term" not in st.session_state: st.session_state.explorer_search_term = ""
if "explorer_option" not in st.session_state: st.session_state.explorer_option = "Select an option..."
if "run_id" not in st.session_state: st.session_state.run_id = 0
if "sidebar_pbix_table_select_viewer" not in st.session_state: st.session_state.sidebar_pbix_table_select_viewer = "Select a table..."
if "current_metadata_context_string" not in st.session_state: st.session_state.current_metadata_context_string = ""
if "pending_rag_reprompt_details" not in st.session_state:
    st.session_state.pending_rag_reprompt_details = None

# --- Helper function for filtering dictionary items ---
def filter_dict_items(items_dict, search_term):
    if not search_term: return items_dict
    search_term_lower = search_term.lower()
    return {
        k: v for k, v in items_dict.items()
        if search_term_lower in str(k).lower() or
           (isinstance(v, str) and search_term_lower in v.lower())
    }

# --- Sidebar UI ---
st.sidebar.title("📊 PBIXplorer Analysis Tool")
st.sidebar.markdown("---")

# Gemini API Key Input
st.sidebar.subheader("Gemini API Configuration")
api_key_input = st.sidebar.text_input(
    "Enter your Gemini API Key", type="password", key="gemini_api_key_widget_ui_v4", value=st.session_state.gemini_api_key
)
if api_key_input and api_key_input != st.session_state.gemini_api_key:
    st.session_state.gemini_api_key = api_key_input
    st.session_state.gemini_configured = False

if st.session_state.gemini_api_key and not st.session_state.gemini_configured:
    with st.spinner("Configuring Gemini Model..."):
        config_success = configure_gemini_model(st.session_state.gemini_api_key)
        if config_success:
            st.session_state.gemini_configured = True
            st.sidebar.success("Gemini model configured!")
        else:
            st.sidebar.error("Failed to configure Gemini. Check API key and console.")
            st.session_state.gemini_configured = False
elif not st.session_state.gemini_api_key:
    st.sidebar.warning("Please enter API Key for PBIXplorer.")
    st.session_state.gemini_configured = False

st.sidebar.markdown("---")
st.sidebar.subheader("File Upload")

# --- File Upload & Processing ---
def on_file_upload_clear():
    if st.session_state.active_file_type is not None:
        st.session_state.pbit_metadata = None; st.session_state.pbix_object = None
        st.session_state.pbix_report_layout = None; st.session_state.active_file_type = None
        st.session_state.original_uploaded_file_name = None; st.session_state.current_metadata_context_string = ""
        st.session_state.chat_history = []; st.session_state.explorer_option = "Select an option..."
        st.session_state.explorer_search_term = ""; st.session_state.sidebar_pbix_table_select_viewer = "Select a table..."
        st.session_state.pending_rag_reprompt_details = None; st.session_state.run_id += 1

uploaded_file = st.sidebar.file_uploader(
    "Choose a .pbit or .pbix file", type=["pbit", "pbix"],
    key="uploaded_file_widget_ui_v4", on_change=on_file_upload_clear
)

if uploaded_file is not None:
    if st.session_state.original_uploaded_file_name != uploaded_file.name or not st.session_state.active_file_type:
        st.session_state.original_uploaded_file_name = uploaded_file.name
        st.session_state.pbit_metadata = None; st.session_state.pbix_object = None
        st.session_state.pbix_report_layout = None; st.session_state.active_file_type = None
        st.session_state.current_metadata_context_string = ""; st.session_state.pending_rag_reprompt_details = None
        st.session_state.explorer_option = "Select an option..."; st.session_state.sidebar_pbix_table_select_viewer = "Select a table..."
        st.session_state.run_id += 1
        initial_bot_message = f"Processing '{uploaded_file.name}'..."
        st.session_state.chat_history = [{"role": "assistant", "content": initial_bot_message}]

        with st.spinner(f"Analyzing '{uploaded_file.name}'... This may take a moment."):
            file_extension = os.path.splitext(uploaded_file.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                tmp_file.write(uploaded_file.getvalue()); temp_file_path = tmp_file.name
            
            report_layout_info_msg = ""; initial_bot_message = f"Okay, I've analyzed **{uploaded_file.name}**. How can I help?"
            processed_data_for_gemini = None
            try:
                if uploaded_file.name.endswith(".pbit"):
                    metadata = parse_pbit_file(temp_file_path)
                    if metadata: st.session_state.pbit_metadata = metadata; st.session_state.active_file_type = "pbit"; processed_data_for_gemini = metadata; st.sidebar.success(f"PBIT '{uploaded_file.name}' parsed!")
                    else: initial_bot_message = f"Could not fully parse PBIT '{uploaded_file.name}'."; st.sidebar.error(f"PBIT parsing failed for {uploaded_file.name}.")
                elif uploaded_file.name.endswith(".pbix"):
                    from pbixray_lib.core import PBIXRay
                    pbix_obj = PBIXRay(temp_file_path)
                    if pbix_obj:
                        st.session_state.pbix_object = pbix_obj; st.session_state.active_file_type = "pbix"; processed_data_for_gemini = pbix_obj
                        try:
                            with zipfile.ZipFile(temp_file_path, 'r') as pbix_zip:
                                st.session_state.pbix_report_layout = extract_report_layout_from_zip(pbix_zip)
                                if st.session_state.pbix_report_layout: report_layout_info_msg = " Report layout also parsed."
                                else: report_layout_info_msg = " Report layout not found/parsed."
                        except Exception: report_layout_info_msg = " Note: Error parsing report layout."
                        initial_bot_message = f"PBIX file **{uploaded_file.name}** analyzed.{report_layout_info_msg} Ready for your questions!"
                        st.sidebar.success(f"PBIX '{uploaded_file.name}' parsed!{report_layout_info_msg}")
                    else: initial_bot_message = f"Could not initialize PBIXRay for '{uploaded_file.name}'."; st.sidebar.error(f"PBIX processing failed for {uploaded_file.name}.")
                
                if st.session_state.active_file_type and processed_data_for_gemini:
                    st.session_state.current_metadata_context_string = format_metadata_for_gemini(
                        processed_data_for_gemini, st.session_state.active_file_type, uploaded_file.name,
                        st.session_state.pbix_report_layout if st.session_state.active_file_type == "pbix" else None)
                else: st.session_state.original_uploaded_file_name = None
            except Exception as e:
                initial_bot_message = f"Error processing '{uploaded_file.name}': {e}"; st.sidebar.error(f"Processing error: {e}")
                st.session_state.active_file_type = None; st.session_state.original_uploaded_file_name = None
            finally:
                if os.path.exists(temp_file_path): os.remove(temp_file_path)
            st.session_state.chat_history = [{"role": "assistant", "content": initial_bot_message}]
            st.rerun()
elif st.session_state.original_uploaded_file_name is not None and uploaded_file is None:
    if st.session_state.active_file_type is not None: on_file_upload_clear(); st.rerun()


# --- Interactive Metadata Explorer in Sidebar ---
if st.session_state.active_file_type:
    st.sidebar.markdown("---"); st.sidebar.subheader("🔍 Explore Metadata")
    EXPLORER_OPTIONS_BASE = ("Select an option...", "Tables & Columns", "Measures", "Calculated Columns", "Relationships", "M Queries", "Report Structure")
    EXPLORER_OPTIONS_PBIX_EXTRA = ("Table Data",)
    if st.session_state.active_file_type == "pbit": EXPLORER_OPTIONS = EXPLORER_OPTIONS_BASE
    elif st.session_state.active_file_type == "pbix": EXPLORER_OPTIONS = EXPLORER_OPTIONS_BASE + EXPLORER_OPTIONS_PBIX_EXTRA
    else: EXPLORER_OPTIONS = ("Select an option...",)
    def on_explorer_option_change_sb():
        st.session_state.explorer_search_term = ""
        if st.session_state.explorer_option != "Table Data": st.session_state.sidebar_pbix_table_select_viewer = "Select a table..."
    st.sidebar.selectbox("Choose metadata:", options=EXPLORER_OPTIONS, key="explorer_option", on_change=on_explorer_option_change_sb)
    if st.session_state.explorer_option != "Table Data": st.sidebar.text_input("Search current view:", key="explorer_search_term")
    search_term_sb = st.session_state.explorer_search_term.lower()
    
    # Tables & Columns
    if st.session_state.explorer_option == "Tables & Columns":
        st.sidebar.markdown("##### Tables and Columns")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            metadata_sb_pbit = st.session_state.pbit_metadata; all_tables = sorted(metadata_sb_pbit.get("tables", []), key=lambda x: x.get("name", ""))
            filtered_tables = [t for t in all_tables if not search_term_sb or search_term_sb in t.get("name", "").lower() or any(search_term_sb in col.get("name","").lower() or search_term_sb in col.get("dataType","").lower() for col in t.get("columns",[]))] if metadata_sb_pbit.get("tables") else []
            if filtered_tables:
                for table in filtered_tables:
                    table_name = table.get("name", "Unknown Table")
                    with st.sidebar.expander(f"Table: **{table_name}** ({len(table.get('columns',[]))} columns)"):
                        if table.get("columns"): cols_data = [{"Column Name": col.get("name"), "Data Type": col.get("dataType")} for col in table["columns"]]; st.dataframe(pd.DataFrame(cols_data), use_container_width=True, height=min(250, (len(cols_data) + 1) * 35 + 3))
                        else: st.write("No columns found.")
            elif search_term_sb and metadata_sb_pbit.get("tables"): st.sidebar.info(f"No tables/columns match '{st.session_state.explorer_search_term}'.")
            elif not metadata_sb_pbit.get("tables"): st.sidebar.info("No table information found.")
        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_md = st.session_state.pbix_object; all_table_names_pbix = sorted(list(pbix_md.tables)); schema_df = pbix_md.schema
            filtered_table_names = [name for name in all_table_names_pbix if not search_term_sb or search_term_sb in name.lower() or any((search_term_sb in col_info['ColumnName'].lower() or search_term_sb in col_info['PandasDataType'].lower()) for _, col_info in schema_df[schema_df['TableName'] == name].iterrows())]
            if filtered_table_names:
                for table_name in filtered_table_names:
                    table_columns_df = schema_df[schema_df['TableName'] == table_name]
                    with st.sidebar.expander(f"Table: **{table_name}** ({len(table_columns_df)} columns)"):
                        if not table_columns_df.empty: cols_data = [{"Column Name": row["ColumnName"], "Data Type": row["PandasDataType"]} for _, row in table_columns_df.iterrows()]; st.dataframe(pd.DataFrame(cols_data), use_container_width=True, height=min(250, (len(cols_data) + 1) * 35 + 3))
                        else: st.write("No columns found.")
            elif search_term_sb and all_table_names_pbix: st.sidebar.info(f"No PBIX tables/columns match '{st.session_state.explorer_search_term}'.")
            elif not all_table_names_pbix: st.sidebar.info("No table information found in PBIX.")
    # Measures
    elif st.session_state.explorer_option == "Measures":
        st.sidebar.markdown("##### DAX Measures")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            metadata_sb_pbit = st.session_state.pbit_metadata; all_measures = metadata_sb_pbit.get("measures", {}); filtered_measures = filter_dict_items(all_measures, search_term_sb)
            if filtered_measures:
                for measure_name, formula in sorted(filtered_measures.items()):
                    with st.sidebar.expander(f"Measure: **{measure_name}**"): st.code(formula, language="dax")
            elif search_term_sb and all_measures : st.sidebar.info(f"No measures match '{st.session_state.explorer_search_term}'.")
            elif not all_measures : st.sidebar.info("No DAX measures found.")
        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_md = st.session_state.pbix_object; dax_measures_df = pbix_md.dax_measures
            if dax_measures_df is not None and not dax_measures_df.empty:
                filtered_measures_df = dax_measures_df[dax_measures_df.apply(lambda row: search_term_sb in f"{row['TableName']}.{row['Name']}".lower() or search_term_sb in str(row['Expression']).lower() or search_term_sb in str(row['DisplayFolder']).lower(), axis=1)] if search_term_sb else dax_measures_df
                if not filtered_measures_df.empty:
                    for _, row in filtered_measures_df.sort_values(by=['TableName', 'Name']).iterrows():
                        measure_qual_name = f"{row['TableName']}.{row['Name']}"
                        with st.sidebar.expander(f"Measure: **{measure_qual_name}**"):
                            if pd.notna(row['DisplayFolder']): st.caption(f"Display Folder: {row['DisplayFolder']}")
                            if pd.notna(row['Description']): st.caption(f"Description: {row['Description']}")
                            st.code(row['Expression'], language="dax")
                elif search_term_sb: st.sidebar.info(f"No PBIX measures match '{st.session_state.explorer_search_term}'.")
            else: st.sidebar.info("No DAX measures found in PBIX.")
    # Calculated Columns
    elif st.session_state.explorer_option == "Calculated Columns":
        st.sidebar.markdown("##### Calculated Columns")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            pbit_meta = st.session_state.pbit_metadata; all_cc = pbit_meta.get("calculated_columns", {}); filtered_cc = filter_dict_items(all_cc, search_term_sb)
            if filtered_cc:
                for cc_name, formula in sorted(filtered_cc.items()):
                    with st.sidebar.expander(f"Calculated Column: **{cc_name}**"): st.code(formula, language="dax")
            elif search_term_sb and all_cc : st.sidebar.info(f"No PBIT CCs match '{st.session_state.explorer_search_term}'.")
            elif not all_cc : st.sidebar.info("No PBIT CCs found.")
        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_obj = st.session_state.pbix_object; dax_columns_df = pbix_obj.dax_columns
            if dax_columns_df is not None and not dax_columns_df.empty:
                filtered_cc_df = dax_columns_df[dax_columns_df.apply(lambda row: search_term_sb in f"{row['TableName']}.{row['ColumnName']}".lower() or search_term_sb in str(row['Expression']).lower(), axis=1)] if search_term_sb else dax_columns_df
                if not filtered_cc_df.empty:
                    for _, row in filtered_cc_df.sort_values(by=['TableName', 'ColumnName']).iterrows():
                        cc_qual_name = f"{row['TableName']}.{row['ColumnName']}"
                        with st.sidebar.expander(f"Calculated Column: **{cc_qual_name}**"): st.code(row['Expression'], language="dax")
                elif search_term_sb: st.sidebar.info(f"No PBIX CCs match '{st.session_state.explorer_search_term}'.")
            else: st.sidebar.info("No CCs found in PBIX.")
    # M Queries
    elif st.session_state.explorer_option == "M Queries" or st.session_state.explorer_option == "M Queries (Power Query)":
        st.sidebar.markdown("##### M (Power Query) Scripts")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            metadata_sb_pbit = st.session_state.pbit_metadata; all_m_queries = sorted(metadata_sb_pbit.get("m_queries", []), key=lambda x: x.get("table_name", ""))
            filtered_m_queries = [mq for mq in all_m_queries if not search_term_sb or search_term_sb in mq.get("table_name","").lower() or search_term_sb in mq.get("script","").lower() or any(search_term_sb in s.lower() for s in mq.get("analysis",{}).get("sources",[])) or any(search_term_sb in t.lower() for t in mq.get("analysis",{}).get("transformations",[]))]
            if filtered_m_queries:
                for mq_info in filtered_m_queries:
                    with st.sidebar.expander(f"M Query for Table: **{mq_info.get('table_name', '?')}**"):
                        analysis = mq_info.get("analysis", {}); st.markdown(f"**Identified Sources:** {', '.join(analysis.get('sources', ['N/A']))}"); st.markdown(f"**Common Transformations:** {', '.join(analysis.get('transformations', ['N/A']))}"); st.markdown("**Script:**"); st.code(mq_info.get("script", "N/A"), language="powerquery")
            elif search_term_sb and metadata_sb_pbit.get("m_queries"): st.sidebar.info(f"No M Queries match '{st.session_state.explorer_search_term}'.")
            elif not metadata_sb_pbit.get("m_queries"): st.sidebar.info("No M Query information found.")
        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_md = st.session_state.pbix_object; power_query_df = pbix_md.power_query
            if power_query_df is not None and not power_query_df.empty:
                filtered_pq_df = power_query_df[power_query_df.apply(lambda row: search_term_sb in str(row['TableName']).lower() or search_term_sb in str(row['Expression']).lower(), axis=1)] if search_term_sb else power_query_df
                if not filtered_pq_df.empty:
                    for _, row in filtered_pq_df.sort_values(by='TableName').iterrows():
                        with st.sidebar.expander(f"M Query for Table: **{row['TableName']}**"): st.code(row['Expression'], language="powerquery")
                elif search_term_sb: st.sidebar.info(f"No PBIX M Queries match '{st.session_state.explorer_search_term}'.")
            else: st.sidebar.info("No M Query information found in PBIX.")
    # Relationships
    elif st.session_state.explorer_option == "Relationships":
        st.sidebar.markdown("##### Relationships")
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
            metadata_sb_pbit = st.session_state.pbit_metadata; all_rels = metadata_sb_pbit.get("relationships", [])
            if not all_rels: st.sidebar.info("No relationships found.")
            else:
                filtered_rels = [r for r in all_rels if not search_term_sb or search_term_sb in str(r.get("fromTable","")).lower() or search_term_sb in str(r.get("toTable","")).lower() or search_term_sb in str(r.get("fromColumn","")).lower() or search_term_sb in str(r.get("toColumn","")).lower()]
                if filtered_rels:
                    rels_data = [{"From": f"{r.get('fromTable','?')}.{r.get('fromColumn','?')}", "To": f"{r.get('toTable','?')}.{r.get('toColumn','?')}", "Active": r.get("isActive", True), "Filter Dir.": r.get("crossFilteringBehavior", "N/A")} for r in filtered_rels]
                    st.sidebar.dataframe(pd.DataFrame(rels_data), use_container_width=True, height=min(300, (len(rels_data) + 1) * 35 + 3))
                elif search_term_sb: st.sidebar.info(f"No relationships match '{st.session_state.explorer_search_term}'.")
        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            pbix_md = st.session_state.pbix_object; relationships_df = pbix_md.relationships
            if relationships_df is not None and not relationships_df.empty:
                filtered_rels_df = relationships_df[relationships_df.apply(lambda row: search_term_sb in str(row['FromTableName']).lower() or search_term_sb in str(row['FromColumnName']).lower() or search_term_sb in str(row['ToTableName']).lower() or search_term_sb in str(row['ToColumnName']).lower(), axis=1)] if search_term_sb else relationships_df
                if not filtered_rels_df.empty:
                    rels_data_pbix = [{"From": f"{r_item.get('FromTableName','?')}.{r_item.get('FromColumnName','?')}", "To": f"{r_item.get('ToTableName','?')}.{r_item.get('ToColumnName','?')}", "Active": r_item.get("IsActive", True), "Cardinality": r_item.get("Cardinality", "N/A"), "Filter Dir.": r_item.get("CrossFilteringBehavior", "N/A")} for _, r_item in filtered_rels_df.iterrows()]
                    st.sidebar.dataframe(pd.DataFrame(rels_data_pbix), use_container_width=True, height=min(300, (len(rels_data_pbix) + 1) * 35 + 3))
                elif search_term_sb: st.sidebar.info(f"No PBIX relationships match '{st.session_state.explorer_search_term}'.")
            else: st.sidebar.info("No relationships found in PBIX.")
    # Report Structure
    elif st.session_state.explorer_option == "Report Structure":
        st.sidebar.markdown("##### Report Structure (Pages & Visuals)")
        report_pages_data = None; source_type_for_msg = ""
        if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata: report_pages_data = st.session_state.pbit_metadata.get("report_pages", []); source_type_for_msg = "PBIT"
        elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_report_layout: report_pages_data = st.session_state.pbix_report_layout; source_type_for_msg = "PBIX"
        if report_pages_data:
            all_pages = sorted(report_pages_data, key=lambda x: x.get("name", "Unnamed Page"))
            filtered_pages = [p for p in all_pages if not search_term_sb or search_term_sb in p.get("name","").lower() or any(search_term_sb in str(v.get("title","")).lower() or search_term_sb in str(v.get("type","")).lower() or any(search_term_sb in f.lower() for f in v.get("fields_used",[])) for v in p.get("visuals",[]))]
            if filtered_pages:
                for page in filtered_pages:
                    page_name = page.get("name", "Unknown Page")
                    with st.sidebar.expander(f"Page: **{page_name}** ({len(page.get('visuals',[]))} visuals)"):
                        if page.get("visuals"):
                            for visual in page["visuals"]:
                                visual_title_or_type = visual.get('title') if visual.get('title') else visual.get('type', 'Unknown Visual'); st.markdown(f"**{visual_title_or_type}** (Type: {visual.get('type', 'N/A')})")
                                fields = visual.get("fields_used", []);
                                if fields: st.caption(f"Fields: {', '.join(f'`{f}`' for f in fields)}")
                                else: st.caption("_No specific fields identified._")
                        else: st.write("No visuals found on this page.")
            elif search_term_sb: st.sidebar.info(f"No report items match '{st.session_state.explorer_search_term}' in {source_type_for_msg}.")
        elif st.session_state.active_file_type == "pbix" and not st.session_state.pbix_report_layout: st.sidebar.info("Report structure (Report/Layout) was not found or parsed from this PBIX file.")
        else: st.sidebar.info(f"No report structure information found in {source_type_for_msg}.")
    # Table Data
    elif st.session_state.explorer_option == "Table Data":
        if st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            st.sidebar.markdown("##### View Table Data (PBIX - First 100 Rows)")
            pbix_obj_for_view = st.session_state.pbix_object; pbix_tables_for_view = sorted(list(pbix_obj_for_view.tables))
            if pbix_tables_for_view:
                table_options = ["Select a table..."] + pbix_tables_for_view
                selected_table_in_sb = st.sidebar.selectbox("Select table to view:", options=table_options, key="sidebar_pbix_table_select_viewer")
                if selected_table_in_sb != "Select a table...":
                    try:
                        with st.spinner(f"Loading first 100 rows of '{selected_table_in_sb}'..."):
                            data_df_sb = pbix_obj_for_view.get_table(selected_table_in_sb).head(100)
                            st.sidebar.caption(f"Displaying first {len(data_df_sb)} rows of **{selected_table_in_sb}**:")
                            st.sidebar.dataframe(data_df_sb, height=300)
                    except Exception as e_sb_table: st.sidebar.error(f"Could not load data for '{selected_table_in_sb}': {e_sb_table}")
            else: st.sidebar.info("No tables found in PBIX to view.")
        else: st.sidebar.info("This option is for PBIX files only.")

# --- Main Page: Chatbot Interface ---
st.header("📊 PBIXplorer Analysis Tool")

if not st.session_state.active_file_type:
    st.info("👈 Upload a .pbit or .pbix file and configure Gemini API Key in the sidebar to begin.")
elif not st.session_state.gemini_configured:
    st.info("👈 Please configure your Gemini API Key in the sidebar to enable PBIXplorer.")
else:
    display_filename = st.session_state.get("original_uploaded_file_name", "N/A")
    file_type_display = st.session_state.active_file_type.upper() if st.session_state.active_file_type else ""
    st.caption(f"Currently analyzing {file_type_display}: **{display_filename}** with PBIXplorer (Gemini).")

    # RAG Re-prompt Logic
    if st.session_state.pending_rag_reprompt_details:
        details = st.session_state.pending_rag_reprompt_details
        tables_to_fetch = details["table_names"]
        original_user_query = details["original_user_query"]
        
        with st.spinner(f"PBIXplorer is analyzing additional data for table(s): {', '.join(tables_to_fetch)}..."):
            fetched_data_strings = []
            if st.session_state.pbix_object and tables_to_fetch:
                for table_name in tables_to_fetch:
                    try:
                        fetched_df = st.session_state.pbix_object.get_table(table_name)
                        df_sample_str = fetched_df.head(MAX_TOOL_FETCHED_ROWS_FOR_REPROMPT).to_string(index=False) # Using to_string for simplicity
                        fetched_data_strings.append(f"--- Data from table: {table_name} ---\n{df_sample_str}\n")
                    except Exception as e_fetch:
                        fetched_data_strings.append(f"--- Error fetching data for table: {table_name} ---\n{e_fetch}\n")
            
            combined_fetched_data_str = "\n".join(fetched_data_strings) if fetched_data_strings else "No additional data could be fetched or was requested."
            chat_history_for_reprompt = format_chat_history_for_prompt(st.session_state.chat_history, MAX_CHAT_HISTORY_TURNS)
            
            reprompt_for_gemini = construct_reprompt_with_fetched_data(
                original_user_query, st.session_state.current_metadata_context_string,
                chat_history_for_reprompt, tables_to_fetch, combined_fetched_data_str
            )
            final_response_text = generate_gemini_response(reprompt_for_gemini)
            st.session_state.chat_history.append({"role": "assistant", "content": final_response_text})
            st.session_state.pending_rag_reprompt_details = None
            st.session_state.run_id +=1
            st.rerun()

    # Chat history display
    chat_box_style = ("max-height: 600px; overflow-y: auto; padding: 10px; "
                      "border-radius: 5px; margin-bottom: 10px;")
    st.markdown(f'<div id="chat-messages-container" style="{chat_box_style}">', unsafe_allow_html=True)
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"]) # Ensure Gemini output is rendered as Markdown
    st.markdown('</div>', unsafe_allow_html=True)

    js_key = f"auto_scroll_js_{st.session_state.run_id}"
    js_autoscroll = f"""<script name="{js_key}"> setTimeout(function() {{
            var chatContainer = document.getElementById("chat-messages-container");
            if (chatContainer) {{ chatContainer.scrollTop = chatContainer.scrollHeight; }}
        }}, 150); </script>"""
    if st.session_state.chat_history:
        st.components.v1.html(js_autoscroll, height=0, scrolling=False)

    if not st.session_state.pending_rag_reprompt_details:
        if prompt := st.chat_input("Ask PBIXplorer about the file or data concepts..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.session_state.run_id += 1
            st.rerun()

    if st.session_state.chat_history and \
       st.session_state.chat_history[-1]["role"] == "user" and \
       not st.session_state.pending_rag_reprompt_details:
        user_query = st.session_state.chat_history[-1]["content"]
        with st.spinner("PBIXplorer is thinking..."):
            if st.session_state.active_file_type and st.session_state.current_metadata_context_string:
                chat_history_for_prompt = format_chat_history_for_prompt(st.session_state.chat_history[:-1], MAX_CHAT_HISTORY_TURNS)
                initial_prompt_for_gemini = construct_initial_prompt(user_query, st.session_state.current_metadata_context_string, chat_history_for_prompt)
                gemini_response_text = generate_gemini_response(initial_prompt_for_gemini)
                tool_request_data = None

                if "// TOOL_REQUEST_START" in gemini_response_text and "// TOOL_REQUEST_END" in gemini_response_text:
                    try:
                        block_start_marker = "// TOOL_REQUEST_START"; block_end_marker = "// TOOL_REQUEST_END"
                        start_of_block_idx = gemini_response_text.find(block_start_marker)
                        content_start_idx = start_of_block_idx + len(block_start_marker)
                        content_end_idx = gemini_response_text.find(block_end_marker, content_start_idx)
                        preliminary_message = gemini_response_text[:start_of_block_idx].strip()
                        if preliminary_message: st.session_state.chat_history.append({"role": "assistant", "content": preliminary_message})

                        if content_end_idx != -1:
                            json_candidate_str = gemini_response_text[content_start_idx:content_end_idx].strip()
                            first_brace = json_candidate_str.find('{'); last_brace = json_candidate_str.rfind('}')
                            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                                actual_json_str = json_candidate_str[first_brace : last_brace+1]
                                tool_request_data = json.loads(actual_json_str)
                            else: gemini_response_text = f"PBIXplorer internal format error. Raw: {json_candidate_str}"
                        else: gemini_response_text = f"PBIXplorer formatting error. Raw: {gemini_response_text}"
                    except json.JSONDecodeError as e_json:
                        print(f"JSONDecodeError: {e_json}\nAttempted: '{actual_json_str if 'actual_json_str' in locals() else json_candidate_str if 'json_candidate_str' in locals() else 'unknown'}'")
                        gemini_response_text = f"PBIXplorer internal data request format error. Details: {e_json}. Raw output: {gemini_response_text}"
                    except Exception as e_tool_parse:
                        print(f"Generic tool parse error: {e_tool_parse}"); gemini_response_text = f"PBIXplorer internal action issue. Raw: {gemini_response_text}"
                
                if tool_request_data and tool_request_data.get("tool_name") == "fetch_tables_for_analysis":
                    params = tool_request_data.get("parameters", {})
                    tables_to_fetch = params.get("table_names", [])
                    if isinstance(tables_to_fetch, str): tables_to_fetch = [tables_to_fetch]
                    reason_for_user = params.get("reason_for_user", f"To proceed, I need more data from table(s): {', '.join(tables_to_fetch) if tables_to_fetch else 'requested tables'}.")
                    if tables_to_fetch:
                        st.session_state.pending_rag_reprompt_details = {"table_names": tables_to_fetch, "original_user_query": user_query, "reason_for_user": reason_for_user}
                        if not ('preliminary_message' in locals() and preliminary_message): st.session_state.chat_history.append({"role": "assistant", "content": reason_for_user})
                        st.session_state.chat_history.append({"role": "assistant", "content": f"*PBIXplorer is now fetching additional data for table(s): **{', '.join(tables_to_fetch)}**...*"})
                    else: st.session_state.chat_history.append({"role": "assistant", "content": "PBIXplorer wanted to fetch more data but didn't specify which tables. Please try rephrasing."})
                else: # No valid tool request, or it's not for fetching tables
                    st.session_state.chat_history.append({"role": "assistant", "content": gemini_response_text})
            else:
                st.session_state.chat_history.append({"role": "assistant", "content": "File data not available or metadata context not prepared."})
            st.session_state.run_id += 1
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("**PBIXplorer Analysis Tool**  \nDeveloped by Marvin Heng  \n*Powered by Gemini*")