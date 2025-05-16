import zipfile
import json
import os
import shutil
import tempfile
import codecs
import re # For regular expressions
from typing import Dict, Any, List, Optional

# --- Constants ---
DATAMODEL_SCHEMA_PATH = "DataModelSchema"
REPORT_LAYOUT_PATH = "Report/Layout"

def strip_all_known_boms(data: bytes) -> (bytes, str):
    """Strips all common BOMs and returns the data and detected encoding."""
    bom_encodings = {
        codecs.BOM_UTF32_LE: 'utf-32-le', codecs.BOM_UTF32_BE: 'utf-32-be',
        codecs.BOM_UTF16_LE: 'utf-16-le', codecs.BOM_UTF16_BE: 'utf-16-be',
        codecs.BOM_UTF8: 'utf-8-sig'
    }
    for bom, encoding in bom_encodings.items():
        if data.startswith(bom): return data[len(bom):], encoding
    return data, None

def safe_extract_json(zip_file: zipfile.ZipFile, path: str) -> Optional[Dict[str, Any]]:
    """Safely extracts and parses a JSON file from the zip archive."""
    cleaned_content_str = "" 
    detected_encoding_final = "unknown"
    content_bytes_original = b''
    try:
        with zip_file.open(path) as f_in:
            content_bytes_original = f_in.read()
            if not content_bytes_original:
                print(f"Warning: File {path} is empty.")
                return None
            content_bytes_no_bom, bom_detected_encoding = strip_all_known_boms(content_bytes_original)
            
            # Order based on previous findings (UTF-16 LE was common for the user)
            if bom_detected_encoding:
                potential_encodings = [bom_detected_encoding]
            else:
                potential_encodings = ['utf-16-le', 'utf-8', 'utf-16-be', 'latin-1', 'cp1252']
            
            content_str = None
            for enc in potential_encodings:
                try:
                    content_str = content_bytes_no_bom.decode(enc)
                    detected_encoding_final = enc
                    break 
                except UnicodeDecodeError: continue 
            
            if content_str is None:
                print(f"Warning: Could not decode content from {path}. Hex: {content_bytes_original[:20].hex()}")
                return None

            start_json_brace = content_str.find('{'); start_json_bracket = content_str.find('[')
            start_index = -1
            if start_json_brace != -1 and start_json_bracket != -1: start_index = min(start_json_brace, start_json_bracket)
            elif start_json_brace != -1: start_index = start_json_brace
            elif start_json_bracket != -1: start_index = start_json_bracket
            
            if start_index != -1:
                if start_index > 0: 
                    # print(f"Info: Stripped leading chars from {path}: {repr(content_str[:start_index])}")
                    pass
                cleaned_content_str = content_str[start_index:]
            else:
                # print(f"Warning: No JSON start in {path}. Content: {repr(content_str[:100])}")
                cleaned_content_str = content_str.strip() 

            if not cleaned_content_str:
                print(f"Warning: Content of {path} empty after strip.")
                return None
            return json.loads(cleaned_content_str)
    except KeyError: print(f"Warning: File not found in PBIT: {path}"); return None
    except json.JSONDecodeError as e:
        error_char_index = e.pos
        context_str_for_error = cleaned_content_str if cleaned_content_str else (content_bytes_original.decode(detected_encoding_final if detected_encoding_final != 'unknown' else 'utf-8', errors='ignore') if content_bytes_original else "")
        context_start = max(0, error_char_index - 30); context_end = min(len(context_str_for_error), error_char_index + 30)
        error_context = context_str_for_error[context_start:context_end]
        print(f"Warning: JSON parse error in {path} (enc: {detected_encoding_final}) - {e}")
        if error_char_index < len(context_str_for_error): print(f" Error near char {error_char_index}: '{repr(context_str_for_error[error_char_index])}'")
        else: print(f" Error at char {error_char_index}.")
        print(f" Context: ...{repr(error_context)}..."); return None
    except Exception as e: import traceback; print(f"Warning: Unexpected error reading {path}: {e}"); traceback.print_exc(); return None

def normalize_field_reference(table: Optional[str], column_or_measure: str) -> str:
    name = str(column_or_measure).replace("'.'", ".").replace("'", "") 
    if table:
        table_cleaned = str(table).replace('\'', '')
        return f"{table_cleaned}.{name}"
    return name

def extract_fields_from_query_selects(select_items: List[Dict[str, Any]]) -> List[str]:
    extracted_fields = set()
    if not isinstance(select_items, list): return []
    for item in select_items:
        if not isinstance(item, dict): continue
        field_name = None; table_name = None
        if "Measure" in item and isinstance(item["Measure"], dict):
            m_d = item["Measure"]; field_name = m_d.get("Property")
            if "Expression" in m_d and isinstance(m_d["Expression"], dict) and "SourceRef" in m_d["Expression"] and isinstance(m_d["Expression"]["SourceRef"], dict): table_name = m_d["Expression"]["SourceRef"].get("Entity")
        elif "Column" in item and isinstance(item["Column"], dict):
            c_d = item["Column"]; field_name = c_d.get("Property")
            if "Expression" in c_d and isinstance(c_d["Expression"], dict) and "SourceRef" in c_d["Expression"] and isinstance(c_d["Expression"]["SourceRef"], dict): table_name = c_d["Expression"]["SourceRef"].get("Entity")
        elif "Aggregation" in item and isinstance(item["Aggregation"], dict):
            a_d = item["Aggregation"]
            if "Expression" in a_d and isinstance(a_d["Expression"], dict) and "Column" in a_d["Expression"] and isinstance(a_d["Expression"]["Column"], dict):
                c_d = a_d["Expression"]["Column"]; field_name = c_d.get("Property")
                if "Expression" in c_d and isinstance(c_d["Expression"], dict) and "SourceRef" in c_d["Expression"] and isinstance(c_d["Expression"]["SourceRef"], dict): table_name = c_d["Expression"]["SourceRef"].get("Entity")
        elif "HierarchyLevel" in item and isinstance(item["HierarchyLevel"], dict):
            hl_d = item["HierarchyLevel"]; l_e = hl_d.get("Expression", {}).get("Level", {})
            if isinstance(l_e, dict) and "Expression" in l_e and isinstance(l_e["Expression"], dict) and "SourceRef" in l_e["Expression"] and isinstance(l_e["Expression"]["SourceRef"], dict):
                table_name = l_e["Expression"]["SourceRef"].get("Entity"); field_name = l_e.get("Level")
            elif "Name" in hl_d: field_name = hl_d.get("Name")
        if field_name: extracted_fields.add(normalize_field_reference(table_name, str(field_name)))
    return list(extracted_fields)

def extract_fields_from_visual_config(visual_config: Dict[str, Any], visual_level_filters_str: Optional[str]) -> List[str]:
    fields = set(); 
    if not isinstance(visual_config, dict): return []
    if "projections" in visual_config and isinstance(visual_config["projections"], dict):
        for _, p_l in visual_config["projections"].items():
            if isinstance(p_l, list):
                for p_i in p_l:
                    if isinstance(p_i, dict) and "queryRef" in p_i:
                        q_r = p_i.get("queryRef"); 
                        if isinstance(q_r, str): fields.add(normalize_field_reference(None, q_r))
    s_v_c = visual_config.get("singleVisual", {})
    if isinstance(s_v_c, dict):
        p_q = s_v_c.get("prototypeQuery", {}); 
        if isinstance(p_q, dict) and "Select" in p_q: fields.update(extract_fields_from_query_selects(p_q["Select"]))
        q_s = s_v_c.get("query", {}); 
        if isinstance(q_s, dict) and "selects" in q_s: fields.update(extract_fields_from_query_selects(q_s["selects"]))
        s_d_o = s_v_c.get("objects", {}).get("data")
        if not s_d_o:
            g_o = s_v_c.get("vcObjects", {}).get("general")
            if isinstance(g_o, list) and g_o: s_d_o = g_o[0].get("properties",{}).get("filterDataSource",{}).get("target")
            elif isinstance(g_o, dict): s_d_o = g_o.get("properties",{}).get("filterDataSource",{}).get("target")
        s_t_p = {}; 
        if isinstance(s_d_o, list) and s_d_o:
            s_t_p_c = s_d_o[0].get("properties", {}).get("target", {})
            s_t_p = s_t_p_c.get("target",{}) if isinstance(s_t_p_c, dict) and "target" in s_t_p_c else s_t_p_c
        elif isinstance(s_d_o, dict): s_t_p = s_d_o
        if isinstance(s_t_p, dict):
            t = s_t_p.get("table"); c = s_t_p.get("column"); m = s_t_p.get("measure"); h = s_t_p.get("hierarchy"); l = s_t_p.get("level")
            if t and c: fields.add(normalize_field_reference(t,c))
            elif t and h and l: fields.add(normalize_field_reference(t,l))
            elif t and m: fields.add(normalize_field_reference(t,m))
            elif m: fields.add(normalize_field_reference(None,m))
    d_t = visual_config.get("dataTransforms", {})
    if isinstance(d_t, dict) and "selects" in d_t:
        for item in d_t.get("selects", []):
            if isinstance(item, dict):
                q_n = item.get("queryName")
                if q_n and isinstance(q_n, str) and ('.' in q_n or not any(c in q_n for c in '()[]{}')): fields.add(normalize_field_reference(None, q_n))
                else:
                    ex = item.get("expr"); 
                    if isinstance(ex, dict): fields.update(extract_fields_from_query_selects([ex]))
                    elif item.get("displayName") and isinstance(item.get("displayName"), str): fields.add(normalize_field_reference(None, item.get("displayName")))
    if visual_level_filters_str:
        try:
            f_l = json.loads(visual_level_filters_str)
            if isinstance(f_l, list):
                for f_i in f_l:
                    if isinstance(f_i, dict):
                        tgt = f_i.get("target"); 
                        if isinstance(tgt, list) and tgt:
                            for t_i in tgt:
                                if isinstance(t_i, dict):
                                    t=t_i.get("table");c=t_i.get("column");m=t_i.get("measure");h=t_i.get("hierarchy");l=t_i.get("level")
                                    if t and c: fields.add(normalize_field_reference(t,c))
                                    elif t and h and l: fields.add(normalize_field_reference(t,l))
                                    elif t and m: fields.add(normalize_field_reference(t,m))
                                    elif m: fields.add(normalize_field_reference(None,m))
                        exp = f_i.get("expression"); 
                        if isinstance(exp, dict): fields.update(extract_fields_from_query_selects([exp]))
        except json.JSONDecodeError: print(f"W: VFilter JSON decode err. Str: {visual_level_filters_str[:100]}...")
        except Exception as e: print(f"W: Err processing VFilters: {e}")
    return list(f for f in fields if f)

def analyze_m_query(m_script: str) -> Dict[str, List[str]]:
    analysis = {"sources": [], "transformations": [], "parameters": []}
    if not m_script: return analysis
    source_patterns = {
        "Excel": r"\bExcel\.(Workbook|Files)\b", "CSV": r"\bCsv\.Document\b",
        "SQL": r"\bSql\.(Database|Databases)\b", "Web": r"\bWeb\.Contents\b",
        "OData": r"\bOData\.Feed\b", "JSON": r"\bJson\.Document\b",
        "XML": r"\bXml\.(Document|Tables)\b", "Folder": r"\bFolder\.Files\b",
        "SharePoint": r"\bSharePoint\.(Files|Tables|Lists)\b",
        "AnalysisServices": r"\bAnalysisServices\.(Databases|Database)\b",
        "DirectInput": r"#\"?\w[\w\s\.]*\"?\(",
        "TableFromRows": r"\bTable\.FromRows\b", "TableFromRecords": r"\bTable\.FromRecords\b",
        "TableFromColumns": r"\bTable\.FromColumns\b",
        "EnterData": r"Table\.FromRows\(Json\.Document\(Binary\.Decompress\(Binary\.FromText\("
    }
    transformation_patterns = {
        "SelectRows": r"\bTable\.SelectRows\b", "RemoveColumns": r"\bTable\.RemoveColumns\b",
        "AddColumn": r"\bTable\.AddColumn\b", "TransformColumns": r"\bTable\.TransformColumns\b",
        "TransformColumnTypes": r"\bTable\.TransformColumnTypes\b", "Group": r"\bTable\.Group\b",
        "Merge": r"\bTable\.NestedJoin\b|\bTable\.Join\b|\bTable\.FuzzyJoin\b",
        "Append": r"\bTable\.Combine\b", "PromoteHeaders": r"\bTable\.PromoteHeaders\b",
        "DemoteHeaders": r"\bTable\.DemoteHeaders\b", "Pivot": r"\bTable\.Pivot\b",
        "Unpivot": r"\bTable\.Unpivot\b|\bTable\.UnpivotOtherColumns\b", "Sort": r"\bTable\.Sort\b",
        "Filter": r"\bTable\.SelectRows\b", "ReplaceValue": r"\bTable\.ReplaceValue\b",
        "SplitColumn": r"\bTable\.SplitColumn\b|\bSplitter\.\w+\b",
        "FillDownUp": r"\bTable\.FillDown\b|\bTable\.FillUp\b",
        "KeepRemoveRows": r"\bTable\.FirstN\b|\bTable\.LastN\b|\bTable\.RemoveFirstN\b|\bTable\.RemoveLastN\b|\bTable\.Range\b|\bTable\.RemoveAlternateRows\b|\bTable\.AlternateRows\b|\bTable\.Distinct\b|\bTable\.RemoveDuplicates\b|\bTable\.KeepDuplicates\b",
        "ChangeType": r"\bTable\.TransformColumnTypes\b", 
        "InvokeCustomFunction": r"\bFunction\.Invoke\b|\b@?\w+\("
    }
    m_script_no_comments = re.sub(r"//.*", "", m_script)
    m_script_no_comments = re.sub(r"/\*.*?\*/", "", m_script_no_comments, flags=re.DOTALL)
    for source_name, pattern in source_patterns.items():
        if re.search(pattern, m_script_no_comments, re.IGNORECASE):
            if source_name == "DirectInput":
                matches = re.findall(r"#\"?([\w\s\.]+)\"?\(", m_script_no_comments, re.IGNORECASE)
                for m in matches:
                    if not any(m.startswith(lib_prefix) for lib_prefix in ["Table.", "List.", "Record.", "Text.", "Expression."]):
                         analysis["sources"].append(f"Reference: {m.strip()}")
            else: analysis["sources"].append(source_name)
    for transform_name, pattern in transformation_patterns.items():
        if re.search(pattern, m_script_no_comments, re.IGNORECASE):
            analysis["transformations"].append(transform_name)
    analysis["sources"] = sorted(list(set(analysis["sources"])))
    analysis["transformations"] = sorted(list(set(analysis["transformations"])))
    return analysis

def parse_pbit_file(pbit_file_path: str) -> Optional[Dict[str, Any]]:
    extracted_metadata = {
        "tables": [], "relationships": [], "measures": {},
        "calculated_columns": {}, "report_pages": [],
        "m_queries": [], 
        "file_name": os.path.basename(pbit_file_path)
    }
    try:
        with zipfile.ZipFile(pbit_file_path, 'r') as pbit_zip:
            data_model_json = safe_extract_json(pbit_zip, DATAMODEL_SCHEMA_PATH)
            if data_model_json and "model" in data_model_json:
                model = data_model_json["model"]
                if "tables" in model and isinstance(model["tables"], list):
                    for table_data in model["tables"]:
                        if not isinstance(table_data, dict): continue
                        table_name = table_data.get("name")
                        columns = []
                        if "columns" in table_data and isinstance(table_data["columns"], list):
                            for col_data in table_data["columns"]:
                                if not isinstance(col_data, dict): continue
                                col_name = col_data.get("name"); col_type = col_data.get("dataType")
                                columns.append({"name": col_name, "dataType": col_type})
                                if col_data.get("type") == "calculated" and "expression" in col_data:
                                    cc_key = normalize_field_reference(table_name, col_name)
                                    extracted_metadata["calculated_columns"][cc_key] = col_data["expression"]
                        extracted_metadata["tables"].append({"name": table_name, "columns": columns})
                        if "partitions" in table_data and isinstance(table_data["partitions"], list):
                            for partition in table_data["partitions"]:
                                if not isinstance(partition, dict): continue
                                source = partition.get("source")
                                if isinstance(source, dict) and source.get("type") == "m":
                                    m_expr_list = source.get("expression"); m_script = ""
                                    if isinstance(m_expr_list, list): m_script = "\n".join(m_expr_list)
                                    elif isinstance(m_expr_list, str): m_script = m_expr_list
                                    if table_name and m_script:
                                        m_analysis = analyze_m_query(m_script)
                                        extracted_metadata["m_queries"].append({
                                            "table_name": table_name, "script": m_script, "analysis": m_analysis
                                        })
                                        break 
                if "tables" in model and isinstance(model["tables"], list): 
                    for table_data in model["tables"]:
                        if not isinstance(table_data, dict): continue
                        table_name = table_data.get("name")
                        if "measures" in table_data and isinstance(table_data["measures"], list):
                            for measure_data in table_data["measures"]:
                                if not isinstance(measure_data, dict): continue
                                measure_name = measure_data.get("name"); measure_expression = measure_data.get("expression")
                                if table_name and measure_name and measure_expression:
                                    measure_key = normalize_field_reference(table_name, measure_name)
                                    extracted_metadata["measures"][measure_key] = measure_expression
                if "relationships" in model and isinstance(model["relationships"], list): 
                    for rel_data in model["relationships"]:
                        if not isinstance(rel_data, dict): continue
                        extracted_metadata["relationships"].append({
                            "fromTable": rel_data.get("fromTable"), "fromColumn": rel_data.get("fromColumn"),
                            "toTable": rel_data.get("toTable"), "toColumn": rel_data.get("toColumn"),
                            "isActive": rel_data.get("isActive", True),
                            "crossFilteringBehavior": rel_data.get("crossFilteringBehavior")
                        })
            else: print(f"W: DataModelSchema issue or 'model' key missing in {DATAMODEL_SCHEMA_PATH}.")
            report_layout_json = safe_extract_json(pbit_zip, REPORT_LAYOUT_PATH)
            if report_layout_json and "sections" in report_layout_json and isinstance(report_layout_json["sections"], list): 
                for section in report_layout_json["sections"]:
                    if not isinstance(section, dict): continue
                    page_name = section.get("displayName"); visuals_on_page = []
                    if "visualContainers" in section and isinstance(section["visualContainers"], list):
                        for vc_idx, vc in enumerate(section["visualContainers"]):
                            if not isinstance(vc, dict): continue
                            try:
                                config_str = vc.get("config", "{}"); config = {} 
                                if isinstance(config_str, str) and config_str.strip():
                                    try: config = json.loads(config_str) 
                                    except json.JSONDecodeError as e_json_config: print(f"W: Inner visual JSON err p'{page_name}',v{vc_idx}:{e_json_config}. Str:{config_str[:100]}"); continue 
                                visual_type = None
                                if isinstance(config, dict): 
                                    visual_type = config.get("visualType") or (config.get("singleVisual", {}).get("visualType") if isinstance(config.get("singleVisual"), dict) else None)
                                if not visual_type: visual_type = vc.get("name") 
                                visual_title = None
                                if isinstance(config, dict) and isinstance(config.get("singleVisual"), dict) and isinstance(config["singleVisual"].get("vcObjects"), dict) and isinstance(config["singleVisual"]["vcObjects"].get("title"), list) and config["singleVisual"]["vcObjects"]["title"]:
                                    t_o_l = config["singleVisual"]["vcObjects"]["title"]
                                    if t_o_l and isinstance(t_o_l[0], dict):
                                        t_p = t_o_l[0].get("properties", {}).get("text", {})
                                        if isinstance(t_p, dict) and "expr" in t_p and isinstance(t_p["expr"], dict) and "Literal" in t_p["expr"] and isinstance(t_p["expr"]["Literal"], dict) and "Value" in t_p["expr"]["Literal"]:
                                            l_v = t_p["expr"]["Literal"].get("Value")
                                            if isinstance(l_v, str): visual_title = l_v.strip("'")
                                v_f_s = vc.get("filters"); f_u = extract_fields_from_visual_config(config, v_f_s)
                                visuals_on_page.append({"type": visual_type, "title": visual_title, "fields_used": list(set(f_u)) })
                            except Exception as e_vc: print(f"W: Could not parse visual p'{page_name}',v{vc_idx}: {e_vc}")
                    extracted_metadata["report_pages"].append({"name": page_name, "visuals": visuals_on_page})
            else: print(f"W: Report/Layout issue or 'sections' key missing in {REPORT_LAYOUT_PATH}.")
        return extracted_metadata
    except FileNotFoundError: print(f"E: PBIT file not found: {pbit_file_path}");
    except zipfile.BadZipFile: print(f"E: Bad PBIT file (not zip): {pbit_file_path}");
    except Exception as e: import traceback; print(f"E during PBIT parsing: {e}"); traceback.print_exc();
    return None

if __name__ == '__main__':
    dummy_pbit_path = "dummy_m_query_test.pbit"
    if not os.path.exists(dummy_pbit_path):
        print(f"Creating dummy PBIT: {dummy_pbit_path} for M query testing...")
        temp_dir = "dummy_m_query_contents"; os.makedirs(temp_dir, exist_ok=True)
        report_dir = os.path.join(temp_dir, "Report"); os.makedirs(report_dir, exist_ok=True)
        model_content = {
            "name": "m-query-model", "model": {"tables": [
                {"name": "SalesFromExcel", "columns": [{"name": "Amount", "dataType": "decimal"}],
                 "partitions": [{"name": "p1", "mode": "import", "source": {"type": "m", "expression": [
                     "let", "    Source = Excel.Workbook(File.Contents(\"C:\\\\data\\\\sales.xlsx\")),",
                     "    Sales_Sheet = Source{[Item=\"Sales\",Kind=\"Sheet\"]}[Data],",
                     "    #\"Promoted Headers\" = Table.PromoteHeaders(Sales_Sheet), // A comment",
                     "    #\"Changed Type\" = Table.TransformColumnTypes(#\"Promoted Headers\",{{\"Amount\", type number}})",
                     "in", "    #\"Changed Type\""
                 ]}}]},
                {"name": "ProductsFromWeb", "columns": [{"name": "ProductName", "dataType": "string"}],
                 "partitions": [{"name": "p2", "mode": "import", "source": {"type": "m", "expression": [
                     "let", "    Source = Json.Document(Web.Contents(\"https://api.example.com/products\")),",
                     "    #\"ToTable\" = Table.FromList(Source, Splitter.SplitByNothing()),",
                     "    /* Multi-line\n       comment here */",
                     "    #\"Expanded\" = Table.ExpandRecordColumn(#\"ToTable\", \"Column1\", {\"ProductName\"})",
                     "in", "    #\"Expanded\""
                 ]}}]},
                {"name": "RefTable", "columns": [{"name":"ID"}], "partitions": [{"name":"p_ref", "mode":"import", "source":{"type":"m", "expression": "let\n Source = SalesFromExcel,\n // Filter out old sales\n Filtered = Table.SelectRows(Source, each [OrderDate] > #date(2022,1,1))\nin Filtered"}}]}
            ]}}
        with open(os.path.join(temp_dir, DATAMODEL_SCHEMA_PATH), 'w', encoding='utf-16-le') as f: json.dump(model_content, f) # Test UTF-16LE no BOM
        report_content = {"sections": [{"displayName": "Page1", "visualContainers": []}]}
        with open(os.path.join(report_dir, "Layout"), 'w', encoding='utf-16-le') as f: json.dump(report_content, f)
        shutil.make_archive(dummy_pbit_path.replace(".pbit", ""), 'zip', root_dir=temp_dir, base_dir='.')
        os.rename(dummy_pbit_path.replace(".pbit", ".zip"), dummy_pbit_path)
        print(f"Created {dummy_pbit_path}"); shutil.rmtree(temp_dir)
    metadata = parse_pbit_file(dummy_pbit_path)
    if metadata:
        print("\n--- M Query Analysis ---")
        if metadata.get("m_queries"):
            for mq in metadata["m_queries"]:
                print(f"\nTable: {mq['table_name']}")
                print(f"  Sources: {mq['analysis']['sources']}")
                print(f"  Transformations: {mq['analysis']['transformations']}")
        else: print("No M Queries found.")  