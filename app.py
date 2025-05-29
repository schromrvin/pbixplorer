import streamlit as st
import os
import tempfile
import pandas as pd
import zipfile # For opening PBIX to get Report/Layout
from pbit_parser import parse_pbit_file, extract_report_layout_from_zip # IMPORT THE NEW FUNCTION
from chatbot_logic import process_query
# from pbixray_lib.core import PBIXRay # Will be imported conditionally

# --- Page Configuration ---
st.set_page_config(page_title="PBIT/PBIX Chatbot & Explorer", layout="wide")

# --- Session State Initialization ---
if "pbit_metadata" not in st.session_state:
    st.session_state.pbit_metadata = None
if "pbix_object" not in st.session_state:
    st.session_state.pbix_object = None
if "pbix_report_layout" not in st.session_state: # For PBIX Report/Layout data
    st.session_state.pbix_report_layout = None
if "active_file_type" not in st.session_state:
    st.session_state.active_file_type = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = None
if "original_uploaded_file_name" not in st.session_state:
    st.session_state.original_uploaded_file_name = None
if "explorer_search_term" not in st.session_state:
    st.session_state.explorer_search_term = ""
if "explorer_option" not in st.session_state:
    st.session_state.explorer_option = "Select an option..."
if "run_id" not in st.session_state:
    st.session_state.run_id = 0
if "view_data_table_name" not in st.session_state:
    st.session_state.view_data_table_name = None
if "sidebar_table_view_select" not in st.session_state:
    st.session_state.sidebar_table_view_select = "Select a table..."

# --- Helper function for filtering dictionary items (for PBIT explorer) ---
def filter_dict_items(items_dict, search_term):
    if not search_term: return items_dict
    search_term_lower = search_term.lower()
    return {
        k: v for k, v in items_dict.items()
        if search_term_lower in str(k).lower() or
           (isinstance(v, str) and search_term_lower in v.lower())
    }

# --- Sidebar UI ---
st.sidebar.title("📊 PBIT/PBIX Analyzer")
st.sidebar.markdown("---")

# --- File Upload in Sidebar ---
def on_file_upload_change():
    if st.session_state.get("pbit_uploader") is None:
        if st.session_state.active_file_type is not None:
            st.session_state.pbit_metadata = None
            st.session_state.pbix_object = None
            st.session_state.pbix_report_layout = None # RESET
            st.session_state.active_file_type = None
            st.session_state.original_uploaded_file_name = None
            st.session_state.chat_history = []
            st.session_state.explorer_option = "Select an option..."
            st.session_state.explorer_search_term = ""
            st.session_state.view_data_table_name = None
            st.session_state.sidebar_table_view_select = "Select a table..."
            st.session_state.run_id += 1

uploaded_file = st.sidebar.file_uploader(
    "Choose a .pbit or .pbix file",
    type=["pbit", "pbix"],
    key="pbit_uploader",
    on_change=on_file_upload_change
)

if uploaded_file is not None:
    if st.session_state.original_uploaded_file_name != uploaded_file.name or st.session_state.active_file_type is None:
        st.session_state.chat_history = []
        st.session_state.original_uploaded_file_name = uploaded_file.name
        st.session_state.pbit_metadata = None
        st.session_state.pbix_object = None
        st.session_state.pbix_report_layout = None # RESET
        st.session_state.active_file_type = None
        st.session_state.explorer_option = "Select an option..."
        st.session_state.explorer_search_term = ""
        st.session_state.view_data_table_name = None
        st.session_state.sidebar_table_view_select = "Select a table..."
        st.session_state.run_id += 1

        with st.spinner(f"Processing '{uploaded_file.name}'..."):
            file_extension = os.path.splitext(uploaded_file.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_file_path = tmp_file.name
            
            report_layout_info_msg = "" # For PBIX report layout status

            try:
                if uploaded_file.name.endswith(".pbit"):
                    st.session_state.active_file_type = "pbit"
                    metadata = parse_pbit_file(temp_file_path)
                    st.session_state.pbit_metadata = metadata
                    if metadata:
                        st.sidebar.success(f"Parsed PBIT '{st.session_state.original_uploaded_file_name}'!")
                        st.session_state.chat_history = [
                            {"role": "assistant", "content": f"Analyzed PBIT '**{st.session_state.original_uploaded_file_name}**'. How can I help you today?"}
                        ]
                    else:
                        st.sidebar.error("Could not parse the PBIT file. Check console for parser warnings.")
                        st.session_state.active_file_type = None; st.session_state.original_uploaded_file_name = None

                elif uploaded_file.name.endswith(".pbix"):
                    from pbixray_lib.core import PBIXRay # Import PBIXRay
                    st.session_state.active_file_type = "pbix"
                    pbix_obj = PBIXRay(temp_file_path)
                    st.session_state.pbix_object = pbix_obj
                    
                    # Attempt to parse Report/Layout from PBIX
                    try:
                        with zipfile.ZipFile(temp_file_path, 'r') as pbix_zip_for_layout:
                            report_layout_data = extract_report_layout_from_zip(pbix_zip_for_layout)
                            if report_layout_data:
                                st.session_state.pbix_report_layout = report_layout_data
                                report_layout_info_msg = "Report layout also parsed."
                            else:
                                report_layout_info_msg = "Report layout not found or could not be parsed."
                    except Exception as e_layout:
                        report_layout_info_msg = f"Error parsing PBIX report layout: {e_layout}"
                        print(f"Warning: Error parsing PBIX report layout: {e_layout}")
                        st.session_state.pbix_report_layout = None

                    st.sidebar.success(f"Parsed PBIX '{st.session_state.original_uploaded_file_name}'! {report_layout_info_msg}")
                    st.session_state.chat_history = [
                        {"role": "assistant", "content": f"Analyzed PBIX '**{st.session_state.original_uploaded_file_name}**'. {report_layout_info_msg} How can I help you today?"}
                    ]
                else: # Should not happen due to file_uploader type filter
                    st.sidebar.error(f"Unsupported file type: {uploaded_file.name}")
                    st.session_state.active_file_type = None; st.session_state.original_uploaded_file_name = None
            except Exception as e:
                st.sidebar.error(f"An error occurred during processing: {e}")
                # import traceback; st.sidebar.text(traceback.format_exc()) # For debugging
                st.session_state.pbit_metadata = None; st.session_state.pbix_object = None
                st.session_state.pbix_report_layout = None; st.session_state.active_file_type = None
                st.session_state.original_uploaded_file_name = None
            finally:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                st.rerun()

elif st.session_state.active_file_type is not None and uploaded_file is None:
    st.rerun()


# --- Interactive Metadata Explorer in Sidebar ---
if st.session_state.active_file_type:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Explore Metadata")

    # Report Structure is now potentially available for both
    EXPLORER_OPTIONS_BASE = ("Select an option...", "Tables & Columns", "Measures", "Calculated Columns",
                               "Relationships", "M Queries", "Report Structure")
    EXPLORER_OPTIONS_PBIX_EXTRA = ("View Table Data",)


    if st.session_state.active_file_type == "pbit":
        EXPLORER_OPTIONS = EXPLORER_OPTIONS_BASE
    elif st.session_state.active_file_type == "pbix":
        # Only add "View Table Data" if it's PBIX
        EXPLORER_OPTIONS = EXPLORER_OPTIONS_BASE + EXPLORER_OPTIONS_PBIX_EXTRA
    else:
        EXPLORER_OPTIONS = ("Select an option...",)

    def on_explorer_option_change():
        st.session_state.explorer_search_term = ""
        if st.session_state.explorer_option != "View Table Data":
            st.session_state.sidebar_table_view_select = "Select a table..."

    st.sidebar.selectbox(
        "Choose metadata to explore:",
        options=EXPLORER_OPTIONS,
        key="explorer_option",
        on_change=on_explorer_option_change
    )

    st.sidebar.text_input(
        "Search current explorer view:",
        key="explorer_search_term"
    )
    search_term_sb = st.session_state.explorer_search_term.lower()

    # --- Display logic based on explorer_option and active_file_type ---
    if st.session_state.explorer_option == "Tables & Columns":
        # ... (This section remains the same as in the previous response) ...
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
            schema_df = pbix_md.schema

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
        # ... (This section remains the same as in the previous response) ...
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
            dax_measures_df = pbix_md.dax_measures_df 
            if not dax_measures_df.empty:
                filtered_measures_df = dax_measures_df[
                    dax_measures_df.apply(lambda row: search_term_sb in f"{row['TableName']}.{row['Name']}".lower() or \
                                                      search_term_sb in str(row['Expression']).lower() or \
                                                      search_term_sb in str(row['DisplayFolder']).lower(), axis=1)
                ] if search_term_sb else dax_measures_df

                if not filtered_measures_df.empty:
                    for _, row in filtered_measures_df.sort_values(by=['TableName', 'Name']).iterrows():
                        measure_qual_name = f"{row['TableName']}.{row['Name']}"
                        with st.sidebar.expander(f"Measure: **{measure_qual_name}**"):
                            if pd.notna(row['DisplayFolder']):
                                st.caption(f"Display Folder: {row['DisplayFolder']}")
                            if pd.notna(row['Description']):
                                st.caption(f"Description: {row['Description']}")
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
            dax_columns_df = pbix_obj.dax_columns_df # DataFrame: TableName, ColumnName, Expression
            if not dax_columns_df.empty:
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

    elif st.session_state.explorer_option == "M Queries" or st.session_state.explorer_option == "M Queries (Power Query)": # Adjusted name for PBIX
        # ... (This section remains the same as in the previous response) ...
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
            power_query_df = pbix_md.power_query 
            if not power_query_df.empty:
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
        # ... (This section remains the same as in the previous response) ...
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
            relationships_df = pbix_md.relationships 
            if not relationships_df.empty:
                filtered_rels_df = relationships_df[
                    relationships_df.apply(lambda row: search_term_sb in str(row['FromTableName']).lower() or \
                                                       search_term_sb in str(row['FromColumnName']).lower() or \
                                                       search_term_sb in str(row['ToTableName']).lower() or \
                                                       search_term_sb in str(row['ToColumnName']).lower(), axis=1)
                ] if search_term_sb else relationships_df

                if not filtered_rels_df.empty:
                    rels_data_pbix = []
                    for _, r in filtered_rels_df.iterrows():
                        rels_data_pbix.append({
                            "From": f"{r.get('FromTableName','?')}.{r.get('FromColumnName','?')}",
                            "To": f"{r.get('ToTableName','?')}.{r.get('ToColumnName','?')}",
                            "Active": r.get("IsActive", True),
                            "Cardinality": r.get("Cardinality", "N/A"),
                            "Filter Dir.": r.get("CrossFilteringBehavior", "N/A")
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
            report_pages_data = st.session_state.pbix_report_layout # This is already the list of pages
            source_type_for_msg = "PBIX"
        
        if report_pages_data:
            all_pages = sorted(report_pages_data, key=lambda x: x.get("name", ""))
            # Generic filtering logic for report pages (same as PBIT before)
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
        else: # No data and not PBIX without layout case
            st.sidebar.info(f"No report structure information found in {source_type_for_msg}.")


    elif st.session_state.explorer_option == "View Table Data":
        # ... (This section remains the same as in the previous response) ...
        if st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
            st.sidebar.markdown("##### View Table Data (PBIX)")
            pbix_tables = sorted(list(st.session_state.pbix_object.tables))
            if pbix_tables:
                table_options = ["Select a table..."] + pbix_tables
                selected_table_to_view = st.sidebar.selectbox(
                    "Select table to view in main area:",
                    options=table_options,
                    key="sidebar_table_view_select" 
                )
                if selected_table_to_view != "Select a table...":
                    if st.sidebar.button(f"Queue '{selected_table_to_view}' for viewing"):
                        st.session_state.view_data_table_name = selected_table_to_view
                        st.sidebar.info(f"'{selected_table_to_view}' is queued. Ask in chat or it will appear below the chat on next interaction.")
            else:
                st.sidebar.info("No tables found in the PBIX file to view.")
        else:
            st.sidebar.info("This option is for PBIX files only.")


# --- Main Page: Chatbot Interface ---
st.header("📊 PBIT/PBIX Chatbot & Explorer")

if not st.session_state.active_file_type:
    st.info("👈 Upload a .pbit or .pbix file using the sidebar to analyze and chat about its metadata.")
else:
    display_filename = st.session_state.get("original_uploaded_file_name", "N/A")
    file_type_display = st.session_state.active_file_type.upper() if st.session_state.active_file_type else ""
    st.caption(f"Currently analyzing {file_type_display}: **{display_filename}**")

    chat_box_style = (
        "max-height: 500px; overflow-y: auto; padding: 10px; "
        "border-radius: 5px; margin-bottom: 10px;"
    )
    st.markdown(f'<div id="chat-messages-container" style="{chat_box_style}">', unsafe_allow_html=True)
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    st.markdown('</div>', unsafe_allow_html=True)

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

    if prompt := st.chat_input("Ask about the PBIT/PBIX metadata..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        response = "Could not process query: No active file or unknown file type."
        with st.spinner("Thinking..."):
            if st.session_state.active_file_type == "pbit" and st.session_state.pbit_metadata:
                response = process_query(prompt, st.session_state.pbit_metadata, "pbit", None) # No extra data for PBIT
            elif st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
                # Pass PBIXRay object and potentially the report layout data
                response = process_query(prompt, st.session_state.pbix_object, "pbix", st.session_state.pbix_report_layout)

        if isinstance(response, str) and response.startswith("DATA_VIEW_REQUEST:"):
            table_to_view = response.split(":", 1)[1]
            st.session_state.chat_history.append({"role": "assistant", "content": f"Preparing to display data for table: **{table_to_view}** (see below)."})
            st.session_state.view_data_table_name = table_to_view
        else:
            st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.session_state.run_id += 1
        st.rerun()

    if st.session_state.view_data_table_name and st.session_state.active_file_type == "pbix" and st.session_state.pbix_object:
        table_name_to_display = st.session_state.view_data_table_name
        with st.container():
            st.markdown("---")
            st.subheader(f"Data for Table: {table_name_to_display}")
            try:
                with st.spinner(f"Loading data for '{table_name_to_display}'... This may take a moment."):
                    if st.session_state.pbix_object:
                        data_df = st.session_state.pbix_object.get_table(table_name_to_display)
                        st.dataframe(data_df)
                    else: st.error("PBIX object not found. Cannot display table data.")
            except Exception as e:
                st.error(f"Could not load or display data for table '{table_name_to_display}': {e}")
        st.session_state.view_data_table_name = None


st.sidebar.markdown("---")
st.sidebar.caption("PBIT/PBIX Analyzer - Developed by Marvin Heng")