from typing import Dict, Any, List, Optional
import pandas as pd

# --- PBIT Specific Helper Functions (Mostly unchanged) ---
def get_all_table_names_pbit(metadata: Dict[str, Any]) -> List[str]:
    return [table['name'] for table in metadata.get('tables', []) if table.get('name')]

def get_all_measure_names_qualified_pbit(metadata: Dict[str, Any]) -> List[str]:
    return list(metadata.get('measures', {}).keys())

def get_all_cc_names_qualified_pbit(metadata: Dict[str, Any]) -> List[str]:
    return list(metadata.get('calculated_columns', {}).keys())

def get_simple_names_from_qualified(qualified_names: List[str]) -> List[str]:
    return list(set(name.split('.')[-1] for name in qualified_names if name and '.' in name))

def get_global_measure_names(qualified_names: List[str]) -> List[str]:
    return list(set(name for name in qualified_names if name and '.' not in name))

def get_all_column_names_from_tables_qualified_pbit(metadata: Dict[str, Any]) -> List[str]:
    qualified_cols = []
    for table in metadata.get('tables', []):
        table_name = table.get('name')
        if table_name:
            for col in table.get('columns', []):
                col_name = col.get('name')
                if col_name: qualified_cols.append(f"{table_name}.{col_name}")
    return list(set(qualified_cols))

def get_all_page_names(metadata_source: Any) -> List[str]: # Modified to handle both PBIT dict and PBIX list
    if isinstance(metadata_source, dict): # PBIT style (metadata.get('report_pages', []))
        return [page['name'] for page in metadata_source.get('report_pages', []) if isinstance(page, dict) and page.get('name')]
    elif isinstance(metadata_source, list): # PBIX report_layout_data style (list of page dicts)
        return [page['name'] for page in metadata_source if isinstance(page, dict) and page.get('name')]
    return []

def get_tables_with_m_queries_pbit(metadata: Dict[str, Any]) -> List[str]:
    return list(set(mq.get("table_name") for mq in metadata.get("m_queries", []) if mq.get("table_name")))

# --- Generic Helper Functions ---
def find_entity(text: str, entities: List[str]) -> Optional[str]:
    text_lower = text.lower()
    sorted_entities = sorted(entities, key=len, reverse=True)
    for entity in sorted_entities:
        if entity.lower() in text_lower: return entity
    return None

def find_entities_in_query(text: str, entity_list: List[str]) -> List[str]:
    found_entities = []; text_lower = text.lower()
    sorted_entities = sorted(entity_list, key=len, reverse=True)
    temp_text_lower = text_lower
    for entity_name in sorted_entities:
        entity_lower = entity_name.lower()
        if entity_lower in temp_text_lower:
            found_entities.append(entity_name)
            temp_text_lower = temp_text_lower.replace(entity_lower, "###FOUND###", 1)
    return list(set(found_entities))


# --- Main Query Processing Function ---
def process_query(query: str, primary_metadata: Any, file_type: str, auxiliary_data: Optional[Any] = None) -> str:
    query_lower = query.lower()

    if file_type == "pbit" and primary_metadata:
        pbit_m = primary_metadata
        table_names = get_all_table_names_pbit(pbit_m)
        tables_with_m = get_tables_with_m_queries_pbit(pbit_m)
        qualified_measure_names = get_all_measure_names_qualified_pbit(pbit_m)
        simple_measure_names_from_qualified = get_simple_names_from_qualified(qualified_measure_names)
        global_measure_names = get_global_measure_names(qualified_measure_names)
        all_simple_measure_names_for_search = list(set(simple_measure_names_from_qualified + global_measure_names))
        qualified_cc_names_pbit = get_all_cc_names_qualified_pbit(pbit_m)
        simple_cc_names_pbit = get_simple_names_from_qualified(qualified_cc_names_pbit)
        page_names_pbit = get_all_page_names(pbit_m) # Use generic helper

        # --- PBIT Specific Intent Handling ---
        if "list calculated columns" in query_lower:
            if qualified_cc_names_pbit: return "Calculated Columns (PBIT):\n" + "\n".join([f"- {n}" for n in sorted(qualified_cc_names_pbit)])
            return "No calculated columns found in PBIT."

        if "formula for calculated column" in query_lower or "dax for column" in query_lower :
            target_cc_key = find_entity(query, qualified_cc_names_pbit)
            if not target_cc_key:
                s_cc_match = find_entity(query, simple_cc_names_pbit)
                if s_cc_match:
                    p_keys = [k for k in qualified_cc_names_pbit if k.lower().endswith(f".{s_cc_match.lower()}")]
                    if len(p_keys) == 1: target_cc_key = p_keys[0]
                    elif len(p_keys) > 1: return f"Ambiguous calculated column '{s_cc_match}'. Options: {', '.join(p_keys)}"
            if target_cc_key and target_cc_key in pbit_m.get("calculated_columns",{}):
                return f"DAX for PBIT calculated column '{target_cc_key}':\n```dax\n{pbit_m['calculated_columns'][target_cc_key]}\n```"
            if find_entity(query, simple_cc_names_pbit + qualified_cc_names_pbit): return "PBIT Calculated column name found, but formula couldn't be retrieved or was ambiguous."
            return "Which PBIT calculated column for formula? (e.g., 'Table.Column')"

        if "list pages" in query_lower:
            if page_names_pbit: return "Pages (PBIT):\n" + "\n".join([f"- {n}" for n in page_names_pbit])
            return "No pages found in PBIT."

        if "visuals on page" in query_lower or "what visuals are on" in query_lower:
            pg_match = find_entity(query, page_names_pbit)
            if pg_match:
                for p_struct in pbit_m.get("report_pages",[]):
                    if p_struct.get("name","").lower() == pg_match.lower():
                        vs = p_struct.get("visuals",[])
                        if vs:
                            v_info = [f"  - Type: {v.get('type','?')}, Title: {v.get('title','N/A')}, Fields: {', '.join(v.get('fields_used',[])) if v.get('fields_used') else 'N/A'}" for v in vs]
                            return f"Visuals on PBIT page '{pg_match}':\n" + "\n".join(v_info)
                        return f"No visuals on PBIT page '{pg_match}'."
                return f"PBIT Page '{pg_match}' not found."
            return "Which PBIT page for visuals?"
        # ... (Other PBIT intents as before) ...
        if "list m queries" in query_lower or "show m queries" in query_lower or "which tables have m queries" in query_lower:
            if tables_with_m: return "Tables with M (Power Query) scripts (PBIT):\n" + "\n".join([f"- {name}" for name in sorted(tables_with_m)])
            return "No M (Power Query) scripts were found in PBIT."
        if "m query for table" in query_lower or "show m script for" in query_lower or "power query for" in query_lower or "get m for" in query_lower:
            table_name_match_m = find_entity(query, tables_with_m)
            if table_name_match_m:
                for mq in pbit_m.get("m_queries", []):
                    if mq.get("table_name", "").lower() == table_name_match_m.lower():
                        analysis = mq.get("analysis", {})
                        sources = analysis.get("sources", [])
                        transforms = analysis.get("transformations", [])
                        resp = f"M Query for table '{table_name_match_m}' (PBIT):\n"
                        resp += f"  Identified Sources: {', '.join(sources) if sources else 'None identified'}\n"
                        resp += f"  Common Transformations: {', '.join(transforms) if transforms else 'None identified'}\n\n"
                        resp += "```m\n" + mq.get("script", "Error: Script not found.") + "\n```"
                        return resp
                return f"M Query info for '{table_name_match_m}' not found despite expectation (PBIT)."
            general_table_match = find_entity(query, table_names) # Using pbit table_names
            if general_table_match: return f"Table '{general_table_match}' found, but no M script associated in parsed PBIT data."
            return "Which table's M script? Ex: 'm query for table SalesData'"

        if "list tables" in query_lower:
            if table_names: return "Tables (PBIT):\n" + "\n".join([f"- {name}" for name in table_names])
            return "No tables found in PBIT."
        if "describe table" in query_lower or "what columns in" in query_lower:
            tbl_match = find_entity(query, table_names)
            if tbl_match:
                for t in pbit_m.get("tables",[]):
                    if t.get("name","").lower()==tbl_match.lower():
                        cols = [f"- {c.get('name','?')}({c.get('dataType','?')})" for c in t.get("columns",[])];
                        return f"Columns in PBIT table '{tbl_match}':\n"+"\n".join(cols) if cols else f"No columns in PBIT table '{tbl_match}'."
                return f"Table '{tbl_match}' not found in PBIT."
            return "Which PBIT table to describe?"
        if "list measures" in query_lower:
            if qualified_measure_names: return "Measures (PBIT):\n" + "\n".join([f"- {name}" for name in qualified_measure_names]); return "No measures in PBIT."
        if ("formula for measure" in query_lower or "show dax for measure" in query_lower) and "column" not in query_lower :
            target_m_key = find_entity(query, qualified_measure_names)
            if not target_m_key:
                s_m_match = find_entity(query, all_simple_measure_names_for_search)
                if s_m_match:
                    p_keys = [k for k in qualified_measure_names if k.lower().endswith(f".{s_m_match.lower()}") or k.lower() == s_m_match.lower()]
                    if len(p_keys) == 1: target_m_key = p_keys[0]
                    elif len(p_keys) > 1: return f"Ambiguous measure '{s_m_match}'. Options: {', '.join(p_keys)}"
            if target_m_key and target_m_key in pbit_m.get("measures",{}): return f"DAX for PBIT measure '{target_m_key}':\n{pbit_m['measures'][target_m_key]}"
            if find_entity(query, all_simple_measure_names_for_search + qualified_measure_names): return "PBIT Measure not found."
            return "Which PBIT measure for formula?"

        if "list relationships" in query_lower or "show relationships" in query_lower or "relationships of" in query_lower or "relationships for table" in query_lower:
            all_rels = pbit_m.get("relationships", [])
            if not all_rels: return "No relationships found in PBIT."
            tbl_match_rel = find_entity(query, table_names); rel_rels = []; hdr = "Relationships (PBIT)"
            if tbl_match_rel:
                hdr = f"Relationships for PBIT table '{tbl_match_rel}'"
                for r_item in all_rels:
                    if (r_item.get('fromTable','').lower() == tbl_match_rel.lower() or r_item.get('toTable','').lower() == tbl_match_rel.lower()): rel_rels.append(r_item)
                if not rel_rels: return f"No relationships for PBIT table '{tbl_match_rel}'."
            else:
                if "relationships of" in query_lower or "relationships for table" in query_lower:
                     if not find_entities_in_query(query, table_names): return "Which PBIT table for relationships?"
                rel_rels = all_rels
            rels_txt = [f"- From '{r_item.get('fromTable','?')}.{r_item.get('fromColumn','?')}' To '{r_item.get('toTable','?')}.{r_item.get('toColumn','?')}' (Active: {r_item.get('isActive', '?')}, Filter: {r_item.get('crossFilteringBehavior', '?')})" for r_item in rel_rels]
            return f"{hdr}:\n" + "\n".join(rels_txt)


    elif file_type == "pbix" and primary_metadata:
        pbix = primary_metadata
        pbix_report_layout = auxiliary_data

        pbix_table_names = sorted(list(pbix.tables))
        pbix_measures_df = pbix.dax_measures # CORRECTED
        pbix_relationships_df = pbix.relationships
        pbix_power_query_df = pbix.power_query
        pbix_schema_df = pbix.schema
        pbix_cc_df = pbix.dax_columns # CORRECTED

        pbix_page_names = []
        if pbix_report_layout:
            pbix_page_names = get_all_page_names(pbix_report_layout) # Use generic helper

        if "list calculated columns" in query_lower:
            if pbix_cc_df is not None and not pbix_cc_df.empty:
                cc_list = [f"- {row['TableName']}.{row['ColumnName']}" for _, row in pbix_cc_df.iterrows()]
                return "Calculated Columns (PBIX):\n" + "\n".join(sorted(cc_list))
            return "No calculated columns found in PBIX."

        if "formula for calculated column" in query_lower or "dax for column" in query_lower:
            potential_cc_str = query_lower.split("column")[-1].strip().replace("'", "").replace("[", ".").replace("]", "")
            found_cc = []
            if pbix_cc_df is not None:
                for _, row in pbix_cc_df.iterrows():
                    full_cc_name = f"{row['TableName']}.{row['ColumnName']}"
                    if potential_cc_str == full_cc_name.lower() or potential_cc_str == row['ColumnName'].lower():
                        found_cc.append(f"DAX for PBIX calculated column '{full_cc_name}':\n```dax\n{row['Expression']}\n```")
            if found_cc: return "\n\n".join(found_cc)
            return f"Calculated column like '{potential_cc_str}' not found or ambiguous in PBIX."

        if "list pages" in query_lower:
            if pbix_page_names: return "Pages (PBIX Report Layout):\n" + "\n".join([f"- {n}" for n in pbix_page_names])
            if pbix_report_layout is None: return "PBIX Report layout was not parsed or is unavailable. Cannot list pages."
            return "No pages found in PBIX report layout."

        if "visuals on page" in query_lower or "what visuals are on" in query_lower:
            if not pbix_report_layout:
                return "PBIX Report layout was not parsed or is unavailable. Cannot get visuals."
            pg_match = find_entity(query, pbix_page_names)
            if pg_match:
                for p_struct in pbix_report_layout:
                    if p_struct.get("name","").lower() == pg_match.lower():
                        vs = p_struct.get("visuals",[])
                        if vs:
                            v_info = [f"  - Type: {v.get('type','?')}, Title: {v.get('title','N/A')}, Fields: {', '.join(v.get('fields_used',[])) if v.get('fields_used') else 'N/A'}" for v in vs]
                            return f"Visuals on PBIX page '{pg_match}':\n" + "\n".join(v_info)
                        return f"No visuals on PBIX page '{pg_match}'."
                return f"PBIX Page '{pg_match}' not found in report layout."
            return "Which PBIX page for visuals? (from report layout)"
        # ... (Other PBIX intents, ensuring correct property access) ...
        if "list tables" in query_lower:
            if pbix_table_names:
                return "Tables in PBIX:\n" + "\n".join([f"- {name}" for name in pbix_table_names])
            return "No tables found in PBIX."

        if "describe table" in query_lower or "what columns in" in query_lower:
            search_query_for_table = query_lower
            if "describe table" in query_lower: search_query_for_table = query_lower.split("describe table",1)[-1]
            elif "what columns in" in query_lower: search_query_for_table = query_lower.split("what columns in",1)[-1]
            matched_table = find_entity(search_query_for_table.strip(), pbix_table_names)
            if matched_table:
                table_cols_df = pbix_schema_df[pbix_schema_df['TableName'] == matched_table]
                if not table_cols_df.empty:
                    cols_info = [f"- {row['ColumnName']} ({row['PandasDataType']})" for _, row in table_cols_df.iterrows()]
                    return f"Columns in PBIX table '{matched_table}':\n" + "\n".join(cols_info)
                return f"No columns found for PBIX table '{matched_table}'."
            return "Which PBIX table to describe? Available: " + ", ".join(pbix_table_names) if pbix_table_names else "No tables found."

        if "list measures" in query_lower:
            if pbix_measures_df is not None and not pbix_measures_df.empty:
                measures_list = [f"- {row['TableName']}.{row['Name']}" for _, row in pbix_measures_df.iterrows()]
                return "DAX Measures in PBIX:\n" + "\n".join(sorted(measures_list))
            return "No DAX measures found in PBIX."

        if ("formula for measure" in query_lower or "show dax for measure" in query_lower) and "column" not in query_lower:
            potential_measure_str = query_lower.split("measure")[-1].strip().replace("'", "")
            found_m = []
            if pbix_measures_df is not None:
                for _, row in pbix_measures_df.iterrows():
                    full_measure_name = f"{row['TableName']}.{row['Name']}"
                    simple_measure_name = row['Name']
                    if potential_measure_str == full_measure_name.lower() or potential_measure_str == simple_measure_name.lower():
                        found_m.append(f"DAX for PBIX measure '{full_measure_name}':\n```dax\n{row['Expression']}\n```")
            if found_m: return "\n\n".join(found_m)
            return f"Measure like '{potential_measure_str}' not found or ambiguous in PBIX."

        if "list relationships" in query_lower or "show relationships" in query_lower:
            if pbix_relationships_df is not None and not pbix_relationships_df.empty:
                rels_text = []
                for _, row in pbix_relationships_df.iterrows():
                    rels_text.append(f"- From '{row['FromTableName']}.{row['FromColumnName']}' To '{row['ToTableName']}.{row['ToColumnName']}' (Active: {row['IsActive']}, Card: {row['Cardinality']}, Filter: {row['CrossFilteringBehavior']})")
                return "Relationships in PBIX:\n" + "\n".join(rels_text)
            return "No relationships found in PBIX."

        if "list m queries" in query_lower or "show m queries" in query_lower :
            if pbix_power_query_df is not None and not pbix_power_query_df.empty:
                m_queries_tables = sorted(list(pbix_power_query_df['TableName'].unique()))
                return "Tables with M Queries in PBIX:\n" + "\n".join([f"- {name}" for name in m_queries_tables])
            return "No M Queries found in PBIX."

        if "m query for table" in query_lower or "show m script for" in query_lower:
            potential_table_name = query_lower.split("table")[-1].strip().replace("'", "")
            m_query_table_names = []
            if pbix_power_query_df is not None:
                 m_query_table_names = list(pbix_power_query_df['TableName'].unique())
            matched_table = find_entity(potential_table_name, m_query_table_names)
            if matched_table and pbix_power_query_df is not None:
                expression = pbix_power_query_df[pbix_power_query_df['TableName'] == matched_table]['Expression'].iloc[0]
                return f"M Query for PBIX table '{matched_table}':\n```m\n{expression}\n```"
            return f"Table '{potential_table_name}' not found with an M query in PBIX."

        # Chatbot "show data for table" can still be used for a potential main area display if you re-enable it
        if "show data for table" in query_lower or "get data for table" in query_lower:
            parts = query_lower.split("table")
            if len(parts) > 1:
                potential_table_name = parts[-1].strip().replace("'", "")
                actual_table_name = find_entity(potential_table_name, pbix_table_names)
                if actual_table_name:
                    # For chatbot, inform user that data can be viewed in sidebar, or trigger main area view if that's re-enabled
                    return f"You can view data for PBIX table '{actual_table_name}' using the 'View Table Data (Sidebar)' option in the explorer."
                    # OR return f"DATA_VIEW_REQUEST:{actual_table_name}" # If you want to re-enable main area view via chat
                else:
                    return f"Table '{potential_table_name}' not found in PBIX. Available tables: {', '.join(pbix_table_names) if pbix_table_names else 'None'}."
            return "Please specify which table's data you want to see, e.g., 'show data for table Sales'."


    # Fallback message
    fallback_message = "Sorry, I didn't understand that. Try asking things like:\n"
    if file_type == "pbit":
        fallback_message += ("- List tables\n"
                             "- Describe table 'X'\n"
                             "- List measures / Formula for measure 'Y'\n"
                             "- List calculated columns / Formula for calculated column 'T.C'\n"
                             "- List M Queries / M Query for table 'X'\n"
                             "- List pages / Visuals on page 'P'")
    elif file_type == "pbix":
        fallback_message += ("- List tables\n"
                             "- Describe table 'X'\n"
                             # "- Show data for table 'Y'\n" # Chat command for data is now informational
                             "- List measures / Formula for measure 'Y'\n"
                             "- List calculated columns / Formula for calculated column 'T.C'\n"
                             "- List M Queries / M Query for table 'X'\n")
        if auxiliary_data: # If pbix_report_layout was passed
            fallback_message += "- List pages / Visuals on page 'P' (from report layout)\n"
    else:
        fallback_message = "No file is currently loaded or the file type is not supported for detailed queries. Please upload a .pbit or .pbix file."
    return fallback_message


if __name__ == '__main__':
    # ... (main test block can be updated to reflect new PBIXRay property names if needed for local testing) ...
    pass