from typing import Dict, Any, List, Optional

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

def get_all_table_names(metadata: Dict[str, Any]) -> List[str]:
    return [table['name'] for table in metadata.get('tables', []) if table.get('name')]

def get_all_measure_names_qualified(metadata: Dict[str, Any]) -> List[str]:
    return list(metadata.get('measures', {}).keys())

def get_all_cc_names_qualified(metadata: Dict[str, Any]) -> List[str]:
    return list(metadata.get('calculated_columns', {}).keys())

def get_simple_names_from_qualified(qualified_names: List[str]) -> List[str]:
    return list(set(name.split('.')[-1] for name in qualified_names if name and '.' in name))

def get_global_measure_names(qualified_names: List[str]) -> List[str]:
    return list(set(name for name in qualified_names if name and '.' not in name))

def get_all_column_names_from_tables_qualified(metadata: Dict[str, Any]) -> List[str]:
    qualified_cols = []
    for table in metadata.get('tables', []):
        table_name = table.get('name')
        if table_name:
            for col in table.get('columns', []):
                col_name = col.get('name')
                if col_name: qualified_cols.append(f"{table_name}.{col_name}")
    return list(set(qualified_cols))

def get_all_page_names(metadata: Dict[str, Any]) -> List[str]:
    return [page['name'] for page in metadata.get('report_pages', []) if page.get('name')]

def get_tables_with_m_queries(metadata: Dict[str, Any]) -> List[str]:
    return list(set(mq.get("table_name") for mq in metadata.get("m_queries", []) if mq.get("table_name")))

def process_query(query: str, metadata: Dict[str, Any]) -> str:
    query_lower = query.lower()
    table_names = get_all_table_names(metadata)
    tables_with_m = get_tables_with_m_queries(metadata)
    qualified_measure_names = get_all_measure_names_qualified(metadata)
    simple_measure_names_from_qualified = get_simple_names_from_qualified(qualified_measure_names)
    global_measure_names = get_global_measure_names(qualified_measure_names)
    all_simple_measure_names_for_search = list(set(simple_measure_names_from_qualified + global_measure_names))
    qualified_cc_names = get_all_cc_names_qualified(metadata)
    simple_cc_names = get_simple_names_from_qualified(qualified_cc_names)
    qualified_table_column_names = get_all_column_names_from_tables_qualified(metadata)
    simple_table_column_names = get_simple_names_from_qualified(qualified_table_column_names)
    all_known_qualified_fields = list(set(qualified_measure_names + qualified_cc_names + qualified_table_column_names))
    all_known_simple_fields = list(set(all_simple_measure_names_for_search + simple_cc_names + simple_table_column_names))
    page_names = get_all_page_names(metadata)

    # M Query Intents
    if "list m queries" in query_lower or "show m queries" in query_lower or "which tables have m queries" in query_lower:
        if tables_with_m: return "Tables with M (Power Query) scripts:\n" + "\n".join([f"- {name}" for name in sorted(tables_with_m)])
        return "No M (Power Query) scripts were found."
    if "m query for table" in query_lower or "show m script for" in query_lower or "power query for" in query_lower or "get m for" in query_lower:
        table_name_match_m = find_entity(query, tables_with_m)
        if table_name_match_m:
            for mq in metadata.get("m_queries", []):
                if mq.get("table_name", "").lower() == table_name_match_m.lower():
                    analysis = mq.get("analysis", {})
                    sources = analysis.get("sources", [])
                    transforms = analysis.get("transformations", [])
                    resp = f"M Query for table '{table_name_match_m}':\n"
                    resp += f"  Identified Sources: {', '.join(sources) if sources else 'None identified'}\n"
                    resp += f"  Common Transformations: {', '.join(transforms) if transforms else 'None identified'}\n\n"
                    resp += "```m\n" + mq.get("script", "Error: Script not found.") + "\n```"
                    return resp
            return f"M Query info for '{table_name_match_m}' not found despite expectation."
        general_table_match = find_entity(query, table_names)
        if general_table_match: return f"Table '{general_table_match}' found, but no M script associated in parsed data."
        return "Which table's M script? Ex: 'm query for table SalesData'"

    # Existing Intents
    if "list tables" in query_lower:
        if table_names: return "Tables:\n" + "\n".join([f"- {name}" for name in table_names]); return "No tables."
    if "describe table" in query_lower or "what columns in" in query_lower:
        tbl_match = find_entity(query, table_names)
        if tbl_match:
            for t in metadata.get("tables",[]): 
                if t.get("name","").lower()==tbl_match.lower(): 
                    cols = [f"- {c.get('name','?')}({c.get('dataType','?')})" for c in t.get("columns",[])]; 
                    return f"Cols in '{tbl_match}':\n"+"\n".join(cols) if cols else f"No cols in '{tbl_match}'."
            return f"Table '{tbl_match}' not found."
        return "Which table to describe?"
    if "list measures" in query_lower:
        if qualified_measure_names: return "Measures:\n" + "\n".join([f"- {name}" for name in qualified_measure_names]); return "No measures."
    if "formula for measure" in query_lower or "show dax for" in query_lower:
        target_m_key = find_entity(query, qualified_measure_names)
        if not target_m_key:
            s_m_match = find_entity(query, all_simple_measure_names_for_search)
            if s_m_match:
                p_keys = [k for k in qualified_measure_names if k.lower().endswith(f".{s_m_match.lower()}") or k.lower() == s_m_match.lower()]
                if len(p_keys) == 1: target_m_key = p_keys[0]
                elif len(p_keys) > 1: return f"Ambiguous measure '{s_m_match}'. Options: {', '.join(p_keys)}"
        if target_m_key and target_m_key in metadata.get("measures",{}): return f"DAX for '{target_m_key}':\n{metadata['measures'][target_m_key]}"
        if find_entity(query, all_simple_measure_names_for_search + qualified_measure_names): return "Measure not found."
        return "Which measure for formula?"
    if "list calculated columns" in query_lower:
        if qualified_cc_names: return "Calc Cols:\n" + "\n".join([f"- {n}: {metadata['calculated_columns'][n]}" for n in qualified_cc_names]); return "No calc cols."
    if "formula for calculated column" in query_lower or "dax for column" in query_lower:
        target_cc_key = find_entity(query, qualified_cc_names)
        if not target_cc_key:
            s_cc_match = find_entity(query, simple_cc_names)
            if s_cc_match:
                p_keys = [k for k in qualified_cc_names if k.lower().endswith(f".{s_cc_match.lower()}")]
                if len(p_keys) == 1: target_cc_key = p_keys[0]
                elif len(p_keys) > 1: return f"Ambiguous calc col '{s_cc_match}'. Options: {', '.join(p_keys)}"
        if target_cc_key and target_cc_key in metadata.get("calculated_columns",{}): return f"DAX for calc col '{target_cc_key}':\n{metadata['calculated_columns'][target_cc_key]}"
        if find_entity(query, simple_cc_names + qualified_cc_names): return "Calc col not found."
        return "Which calc col for formula?"
    if "list relationships" in query_lower or "show relationships" in query_lower or "relationships of" in query_lower or "relationships for table" in query_lower:
        all_rels = metadata.get("relationships", [])
        if not all_rels: return "No relationships found."
        tbl_match_rel = find_entity(query, table_names); rel_rels = []; hdr = "Relationships"
        if tbl_match_rel:
            hdr = f"Relationships for '{tbl_match_rel}'"
            for r in all_rels:
                if (r.get('fromTable','').lower() == tbl_match_rel.lower() or r.get('toTable','').lower() == tbl_match_rel.lower()): rel_rels.append(r)
            if not rel_rels: return f"No relationships for '{tbl_match_rel}'."
        else:
            if "relationships of" in query_lower or "relationships for table" in query_lower:
                 if not find_entities_in_query(query, table_names): return "Which table for relationships?"
            rel_rels = all_rels
        rels_txt = [f"- From '{r.get('fromTable','?')}.{r.get('fromColumn','?')}' To '{r.get('toTable','?')}.{r.get('toColumn','?')}' (Active: {r.get('isActive', '?')}, Filter: {r.get('crossFilteringBehavior', '?')})" for r in rel_rels]
        return f"{hdr}:\n" + "\n".join(rels_txt)
    if "list pages" in query_lower:
        if page_names: return "Pages:\n" + "\n".join([f"- {n}" for n in page_names]); return "No pages."
    if "visuals on page" in query_lower or "what visuals are on" in query_lower:
        pg_match = find_entity(query, page_names)
        if pg_match:
            for p in metadata.get("report_pages",[]):
                if p.get("name","").lower() == pg_match.lower():
                    vs = p.get("visuals",[])
                    if vs: v_info = [f"  - Type: {v.get('type','?')}, Title: {v.get('title','N/A')}, Fields: {', '.join(v.get('fields_used',[])) if v.get('fields_used') else 'N/A'}" for v in vs]; return f"Visuals on '{pg_match}':\n" + "\n".join(v_info)
                    return f"No visuals on '{pg_match}'."
            return f"Page '{pg_match}' not found."
        return "Which page for visuals?"
    if "where is column" in query_lower or "where is measure" in query_lower or "visuals use field" in query_lower or "which visuals use" in query_lower:
        s_f_q = find_entity(query, all_known_qualified_fields); s_f_s = None
        if not s_f_q: s_f_s = find_entity(query, all_known_simple_fields)
        f_t_s_f_l = None; s_t_d = None
        if s_f_q: f_t_s_f_l = s_f_q.lower(); s_t_d = s_f_q
        elif s_f_s:
            p_q_m = [qf for qf in all_known_qualified_fields if qf.lower().endswith(f".{s_f_s.lower()}") or qf.lower() == s_f_s.lower()]
            if len(p_q_m) == 1: f_t_s_f_l = p_q_m[0].lower(); s_t_d = p_q_m[0]
            elif len(p_q_m) > 1: return f"Ambiguous field '{s_f_s}'. Options: {', '.join(p_q_m)}"
            else: f_t_s_f_l = s_f_s.lower(); s_t_d = s_f_s
        if not f_t_s_f_l: return "Which field for usage?"
        res = []
        for p in metadata.get("report_pages", []):
            for v in p.get("visuals", []):
                for f_i_v_p in v.get("fields_used", []):
                    f_i_v_l = f_i_v_p.lower()
                    if f_t_s_f_l == f_i_v_l or (not '.' in f_t_s_f_l and f_i_v_l.endswith(f".{f_t_s_f_l}")) or ('.' in f_t_s_f_l and f_i_v_l == f_t_s_f_l.split('.')[-1]):
                        v_id = f"'{v.get('title', v.get('type', '?'))}' on page '{p.get('name','?')}'"; f_txt = f"- Field '{s_t_d}' (as '{f_i_v_p}') in visual {v_id}."
                        if f_txt not in res: res.append(f_txt)
        if res: return f"Usage of '{s_t_d}':\n" + "\n".join(res)
        return f"Field '{s_t_d}' not found in visuals."

    # Fallback
    return ("Sorry, I didn't understand that. Try asking things like:\n"
            "- List tables / Describe table 'X'\n"
            "- List measures / Formula for measure 'Y'\n"
            "- List calculated columns\n"
            "- List relationships / List relationships for table 'X'\n"
            "- List M Queries / M Query for table 'X'\n"
            "- List pages / Visuals on page 'P'\n"
            "- Where is column 'T.C' used / Which visuals use measure 'M'")

if __name__ == '__main__':
    dummy_metadata = {
        "tables": [{"name": "SalesData"}, {"name": "ProductInfo"}, {"name": "WebSourceTable"}],
        "m_queries": [
            {"table_name": "SalesData", "script": "let Src=Excel.Workbook(\"s.xlsx\") in Src", "analysis": {"sources": ["Excel"], "transformations": []}},
            {"table_name": "ProductInfo", "script": "let Src=Sql.Database(\"srv\",\"db\") in Src", "analysis": {"sources": ["SQL"], "transformations": []}}
        ], "measures": {"SalesData.TotalAmount": "SUM(SalesData[Amount])"}, "relationships": [],
        "report_pages": [], "calculated_columns": {}, "file_name": "dummy.pbit"
    }
    queries = ["list m queries", "m query for table SalesData", "power query for WebSourceTable", "list tables"]
    print("--- Chatbot Logic Test (M Queries Focus) ---")
    for q_idx, q in enumerate(queries):
        print(f"\n--- Query {q_idx+1} ---\nUSER: {q}\nBOT: {process_query(q, dummy_metadata)}")