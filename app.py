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
if "explorer_search_term" not in st.session_state: 
    st.session_state.explorer_search_term = ""
# Initialize explorer_option correctly
if "explorer_option" not in st.session_state: 
    st.session_state.explorer_option = "Select an option..."


# --- Helper function for filtering ---
def filter_dict_items(items_dict, search_term):
    if not search_term:
        return items_dict
    search_term_lower = search_term.lower()
    return {k: v for k, v in items_dict.items() if search_term_lower in str(k).lower() or search_term_lower in str(v).lower()}

# --- Sidebar UI ---
st.sidebar.title("PBIT Tools 🛠️")
st.sidebar.markdown("---")

# --- File Upload in Sidebar ---
uploaded_file = st.sidebar.file_uploader("Choose a .pbit file", type=["pbit"], key="pbit_uploader")

if uploaded_file is not None:
    if st.session_state.uploaded_file_name != uploaded_file.name or st.session_state.pbit_metadata is None:
        st.session_state.chat_history = [] 
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.pbit_metadata = None 
        
        with st.spinner(f"Processing '{uploaded_file.name}'..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pbit") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_file_path = tmp_file.name
            try:
                metadata = parse_pbit_file(temp_file_path)
                st.session_state.pbit_metadata = metadata
                if metadata:
                    st.sidebar.success(f"Parsed '{uploaded_file.name}'!")
                    st.session_state.chat_history = [
                        {"role": "assistant", "content": f"Analyzed '{metadata.get('file_name', 'your file')}'. How can I help?"}
                    ]
                    # Reset explorer options on new file, ensuring it's a valid default
                    st.session_state.explorer_option = "Select an option..." 
                    st.session_state.explorer_search_term = ""
                else:
                    st.sidebar.error("Could not parse PBIT.")
                    st.session_state.pbit_metadata = None
            except Exception as e:
                st.sidebar.error(f"Processing error: {e}")
                st.session_state.pbit_metadata = None
            finally:
                if os.path.exists(temp_file_path): os.remove(temp_file_path)
                st.rerun() 
else:
    if not st.session_state.pbit_metadata and st.session_state.uploaded_file_name is None :
        pass 

# --- Interactive Metadata Explorer in Sidebar ---
if st.session_state.pbit_metadata:
    metadata_sb = st.session_state.pbit_metadata
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Explore Metadata")
    
    EXPLORER_OPTIONS = ("Select an option...", "Tables & Columns", "Measures", "Calculated Columns", 
                        "Relationships", "M Queries", "Report Structure")

    # Determine the current index for the selectbox
    current_explorer_option_value = st.session_state.get("explorer_option", EXPLORER_OPTIONS[0])
    try:
        current_index = EXPLORER_OPTIONS.index(current_explorer_option_value)
    except ValueError: # If the saved option is somehow invalid, default to the first
        current_index = 0
        st.session_state.explorer_option = EXPLORER_OPTIONS[0]


    # Update session state directly from selectbox's return value
    # The `on_change` callback can also be used for more complex state updates if needed.
    # Here, we directly assign the result to manage the state.
    selected_option = st.sidebar.selectbox(
        "Choose metadata to explore:",
        options=EXPLORER_OPTIONS,
        index=current_index, 
        key="sb_explore_selectbox" # A unique key for the selectbox itself
    )
    # Update the session state if the selection changed
    if selected_option != st.session_state.explorer_option:
        st.session_state.explorer_option = selected_option
        st.session_state.explorer_search_term = "" # Reset search on new category
        st.rerun() # Rerun to reflect the new selection and clear search

    # Use the persisted search term
    st.session_state.explorer_search_term = st.sidebar.text_input(
        "Search explorer:", 
        value=st.session_state.explorer_search_term,
        key="sb_explorer_search_input"
    )
    search_term_sb = st.session_state.explorer_search_term

    # --- Display logic based on st.session_state.explorer_option ---
    # (The content of these if/elif blocks remains the same as your previous full version)
    # Ensure they all use st.session_state.explorer_option for their conditions

    if st.session_state.explorer_option == "Tables & Columns":
        st.sidebar.markdown("##### Tables and Columns")
        all_tables = sorted(metadata_sb.get("tables", []), key=lambda x: x.get("name", ""))
        filtered_tables = []
        if search_term_sb:
            search_term_lower_sb = search_term_sb.lower()
            for table in all_tables:
                if search_term_lower_sb in table.get("name", "").lower() or \
                   any(search_term_lower_sb in col.get("name","").lower() for col in table.get("columns",[])):
                    filtered_tables.append(table)
        else:
            filtered_tables = all_tables
        if filtered_tables:
            for table in filtered_tables:
                table_name = table.get("name", "Unknown Table")
                with st.sidebar.expander(f"Table: {table_name} ({len(table.get('columns',[]))} cols)"):
                    if table.get("columns"):
                        cols_data = [{"Column": col.get("name"), "Type": col.get("dataType")} for col in table["columns"]]
                        st.dataframe(pd.DataFrame(cols_data), use_container_width=True, height=min(250, (len(cols_data) + 1) * 35 + 3))
                    else: st.write("No columns.")
        elif search_term_sb : st.sidebar.info(f"No tables match '{search_term_sb}'.")
        else: st.sidebar.info("No table data.")

    elif st.session_state.explorer_option == "Measures":
        st.sidebar.markdown("##### DAX Measures")
        all_measures = metadata_sb.get("measures", {})
        filtered_measures = filter_dict_items(all_measures, search_term_sb)
        if filtered_measures:
            for measure_name, formula in sorted(filtered_measures.items()):
                with st.sidebar.expander(f"Measure: {measure_name}"):
                    st.code(formula, language="dax")
        elif search_term_sb : st.sidebar.info(f"No measures match '{search_term_sb}'.")
        else: st.sidebar.info("No DAX measures.")

    elif st.session_state.explorer_option == "Calculated Columns":
        st.sidebar.markdown("##### Calculated Columns")
        all_cc = metadata_sb.get("calculated_columns", {})
        filtered_cc = filter_dict_items(all_cc, search_term_sb)
        if filtered_cc:
            for cc_name, formula in sorted(filtered_cc.items()):
                with st.sidebar.expander(f"Calc Col: {cc_name}"):
                    st.code(formula, language="dax")
        elif search_term_sb : st.sidebar.info(f"No calc cols match '{search_term_sb}'.")
        else: st.sidebar.info("No calculated columns.")
    
    elif st.session_state.explorer_option == "Relationships":
        st.sidebar.markdown("##### Relationships")
        if metadata_sb and "relationships" in metadata_sb:
            all_rels = metadata_sb.get("relationships", [])
            if not all_rels:
                st.sidebar.info("No relationships found in PBIT.")
            else:
                filtered_rels = []
                if search_term_sb:
                    s_t_l_sb = search_term_sb.lower()
                    for rel in all_rels:
                        if s_t_l_sb in str(rel.get("fromTable","")).lower() or \
                           s_t_l_sb in str(rel.get("toTable","")).lower() or \
                           s_t_l_sb in str(rel.get("fromColumn","")).lower() or \
                           s_t_l_sb in str(rel.get("toColumn","")).lower() or \
                           s_t_l_sb in str(rel.get("crossFilteringBehavior","")).lower() or \
                           s_t_l_sb in str(rel.get("isActive","")).lower():
                            filtered_rels.append(rel)
                else:
                    filtered_rels = all_rels
                if filtered_rels:
                    rels_data = [{"From": f"{r.get('fromTable','?')}.{r.get('fromColumn','?')}",
                                  "To": f"{r.get('toTable','?')}.{r.get('toColumn','?')}",
                                  "Active": r.get("isActive", True), 
                                  "Filter Dir.": r.get("crossFilteringBehavior", "N/A")}
                                 for r in filtered_rels]
                    df_rels = pd.DataFrame(rels_data)
                    st.sidebar.dataframe(df_rels, use_container_width=True, height=min(300, (len(df_rels) + 1) * 35 + 3))
                elif search_term_sb:
                    st.sidebar.info(f"No relationships match '{search_term_sb}'.")
        else:
            st.sidebar.info("Relationship data missing/invalid.")

    elif st.session_state.explorer_option == "M Queries":
        st.sidebar.markdown("##### M (Power Query) Scripts")
        all_m_queries = sorted(metadata_sb.get("m_queries", []), key=lambda x: x.get("table_name", ""))
        filtered_m_queries = []
        if search_term_sb:
            s_t_l_sb = search_term_sb.lower()
            for mq in all_m_queries:
                if s_t_l_sb in mq.get("table_name","").lower() or s_t_l_sb in mq.get("script","").lower() or \
                   any(s_t_l_sb in s.lower() for s in mq.get("analysis",{}).get("sources",[])) or \
                   any(s_t_l_sb in t.lower() for t in mq.get("analysis",{}).get("transformations",[])):
                    filtered_m_queries.append(mq)
        else:
            filtered_m_queries = all_m_queries
        if filtered_m_queries:
            for mq_info in filtered_m_queries:
                with st.sidebar.expander(f"M Query: {mq_info.get('table_name', '?')}"):
                    analysis = mq_info.get("analysis", {})
                    st.markdown(f"**Src:** {', '.join(analysis.get('sources', ['N/A']))}")
                    st.markdown(f"**Transf:** {', '.join(analysis.get('transformations', ['N/A']))}")
                    st.code(mq_info.get("script", "N/A"), language="powerquery")
        elif search_term_sb : st.sidebar.info(f"No M Queries match '{search_term_sb}'.")
        else: st.sidebar.info("No M Queries.")

    elif st.session_state.explorer_option == "Report Structure":
        st.sidebar.markdown("##### Report Structure")
        all_pages = sorted(metadata_sb.get("report_pages", []), key=lambda x: x.get("name", ""))
        filtered_pages = []
        if search_term_sb:
            s_t_l_sb = search_term_sb.lower()
            for page in all_pages:
                if s_t_l_sb in page.get("name","").lower() or \
                   any(s_t_l_sb in str(v.get("title","")).lower() or \
                       s_t_l_sb in str(v.get("type","")).lower() or \
                       any(s_t_l_sb in f.lower() for f in v.get("fields_used",[])) for v in page.get("visuals",[])):
                    filtered_pages.append(page)
        else:
            filtered_pages = all_pages
        if filtered_pages:
            for page in filtered_pages:
                with st.sidebar.expander(f"Page: {page.get('name', '?')} ({len(page.get('visuals',[]))} visuals)"):
                    if page.get("visuals"):
                        for visual in page["visuals"]:
                            v_title = visual.get('title') or visual.get('type', 'Unknown')
                            st.markdown(f"**{v_title}** (Type: {visual.get('type', 'N/A')})")
                            fields = visual.get("fields_used", [])
                            if fields: st.caption(f"Fields: {', '.join(f'`{f}`' for f in fields)}")
                            else: st.caption("_No fields identified._")
                    else: st.write("No visuals.")
        elif search_term_sb : st.sidebar.info(f"No report items match '{search_term_sb}'.")
        else: st.sidebar.info("No report structure.")


# --- Main Page: Chatbot Interface ---
st.header("💬 PBIT Chatbot")
if not st.session_state.pbit_metadata:
    st.info("☝️ Upload a .pbit file using the sidebar to analyze and chat about its metadata.")
else:
    st.caption(f"Currently analyzing: **{st.session_state.pbit_metadata.get('file_name', 'N/A')}**")
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    if prompt := st.chat_input("Ask about the PBIT metadata..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."): response = process_query(prompt, st.session_state.pbit_metadata)
            st.markdown(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})

st.sidebar.markdown("---")
st.sidebar.caption("Created with Streamlit.")