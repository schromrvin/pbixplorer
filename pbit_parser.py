import zipfile
import json
import os
import shutil
import tempfile
import codecs # For more control over BOM stripping
from typing import Dict, Any, List, Optional

# --- Constants for file paths within PBIT ---
DATAMODEL_SCHEMA_PATH = "DataModelSchema"
REPORT_LAYOUT_PATH = "Report/Layout"

def strip_all_known_boms(data: bytes) -> (bytes, str):
    """
    Strips all common BOMs and returns the data and detected encoding.
    """
    # Order matters: more specific (longer) BOMs first
    bom_encodings = {
        codecs.BOM_UTF32_LE: 'utf-32-le',
        codecs.BOM_UTF32_BE: 'utf-32-be',
        codecs.BOM_UTF16_LE: 'utf-16-le', # FF FE
        codecs.BOM_UTF16_BE: 'utf-16-be', # FE FF
        codecs.BOM_UTF8: 'utf-8-sig'      # EF BB BF
    }
    for bom, encoding in bom_encodings.items():
        if data.startswith(bom):
            # print(f"BOM detected: {encoding} for {bom.hex()}")
            return data[len(bom):], encoding
    return data, None # No known BOM found

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
            
            # If a BOM was detected, use that encoding primarily
            if bom_detected_encoding:
                # print(f"Info: Using BOM-detected encoding '{bom_detected_encoding}' for {path}.")
                potential_encodings = [bom_detected_encoding]
            else:
                # print(f"Info: No BOM detected for {path}. Will try common encodings.")
                # If no BOM, UTF-16 LE is a strong candidate based on observed hex.
                # Also common: UTF-8.
                potential_encodings = ['utf-16-le', 'utf-8', 'utf-16-be', 'latin-1', 'cp1252']
            
            content_str = None
            for enc in potential_encodings:
                try:
                    content_str = content_bytes_no_bom.decode(enc)
                    detected_encoding_final = enc
                    # print(f"Successfully decoded {path} with {detected_encoding_final}.")
                    break 
                except UnicodeDecodeError:
                    # print(f"Failed to decode {path} with {enc}.")
                    continue 
            
            if content_str is None:
                print(f"Warning: Could not decode content from {path} with any attempted encodings.")
                print(f"         First 20 bytes (hex) of {path}: {content_bytes_original[:20].hex()}")
                return None
            
            start_json_brace = content_str.find('{')
            start_json_bracket = content_str.find('[')
            start_index = -1

            if start_json_brace != -1 and start_json_bracket != -1:
                start_index = min(start_json_brace, start_json_bracket)
            elif start_json_brace != -1:
                start_index = start_json_brace
            elif start_json_bracket != -1:
                start_index = start_json_bracket
            
            if start_index != -1:
                if start_index > 0:
                    # print(f"Info: Stripped leading characters from {path}. Content stripped: {repr(content_str[:start_index])}")
                    pass # Suppress this message if it's just whitespace from UTF-16 decoding
                cleaned_content_str = content_str[start_index:]
            else:
                print(f"Warning: No JSON starting character ('{{' or '[') found in decoded content of {path}.")
                # print(f"         Decoded content start (first 100 chars): {repr(content_str[:100])}")
                cleaned_content_str = content_str.strip() 

            if not cleaned_content_str:
                print(f"Warning: Content of {path} is empty after aggressive stripping.")
                return None
            
            # print(f"Cleaned content for {path} starts with: {repr(cleaned_content_str[:20])}")
            return json.loads(cleaned_content_str)

    except KeyError:
        print(f"Warning: File not found in PBIT: {path}")
        return None
    except json.JSONDecodeError as e:
        error_char_index = e.pos
        context_str_for_error = cleaned_content_str if cleaned_content_str else (content_bytes_original.decode(detected_encoding_final if detected_encoding_final != 'unknown' else 'utf-8', errors='ignore') if content_bytes_original else "")
        
        context_start = max(0, error_char_index - 30)
        context_end = min(len(context_str_for_error), error_char_index + 30)
        error_context = context_str_for_error[context_start:context_end]
        
        print(f"Warning: Could not parse JSON from: {path} (tried encoding: {detected_encoding_final}) - Error: {e}")
        if error_char_index < len(context_str_for_error):
            print(f"         Error near character {error_char_index}: '{repr(context_str_for_error[error_char_index])}'")
        else:
            print(f"         Error at character {error_char_index} (possibly at end of file or after stripping).")
        print(f"         Context: ...{repr(error_context)}...")
        # print(f"         First 20 bytes (hex) of original file {path}: {content_bytes_original[:20].hex()}")
        return None
    except Exception as e:
        import traceback
        print(f"Warning: An unexpected error occurred while reading/parsing {path}: {e}")
        traceback.print_exc()
        return None

# --- PASTE THE REST OF pbit_parser.py FROM THE PREVIOUS FULL SCRIPT HERE ---
# (normalize_field_reference, extract_fields_from_query_selects, 
#  extract_fields_from_visual_config, parse_pbit_file, and __main__ block)

def normalize_field_reference(table: Optional[str], column_or_measure: str) -> str:
    name = str(column_or_measure).replace("'.'", ".").replace("'", "") 
    if table:
        table_cleaned = str(table).replace('\'', '')
        return f"{table_cleaned}.{name}"
    return name

def extract_fields_from_query_selects(select_items: List[Dict[str, Any]]) -> List[str]:
    extracted_fields = set()
    if not isinstance(select_items, list):
        return []
    for item in select_items:
        if not isinstance(item, dict):
            continue
        field_name = None
        table_name = None
        if "Measure" in item and isinstance(item["Measure"], dict):
            measure_data = item["Measure"]
            field_name = measure_data.get("Property")
            if "Expression" in measure_data and isinstance(measure_data["Expression"], dict) and \
               "SourceRef" in measure_data["Expression"] and isinstance(measure_data["Expression"]["SourceRef"], dict):
                table_name = measure_data["Expression"]["SourceRef"].get("Entity")
        elif "Column" in item and isinstance(item["Column"], dict):
            col_data = item["Column"]
            field_name = col_data.get("Property")
            if "Expression" in col_data and isinstance(col_data["Expression"], dict) and \
               "SourceRef" in col_data["Expression"] and isinstance(col_data["Expression"]["SourceRef"], dict):
                table_name = col_data["Expression"]["SourceRef"].get("Entity")
        elif "Aggregation" in item and isinstance(item["Aggregation"], dict):
            agg_data = item["Aggregation"]
            if "Expression" in agg_data and isinstance(agg_data["Expression"], dict) and \
               "Column" in agg_data["Expression"] and isinstance(agg_data["Expression"]["Column"], dict):
                col_data = agg_data["Expression"]["Column"]
                field_name = col_data.get("Property")
                if "Expression" in col_data and isinstance(col_data["Expression"], dict) and \
                   "SourceRef" in col_data["Expression"] and isinstance(col_data["Expression"]["SourceRef"], dict):
                    table_name = col_data["Expression"]["SourceRef"].get("Entity")
        elif "HierarchyLevel" in item and isinstance(item["HierarchyLevel"], dict):
            hl_data = item["HierarchyLevel"]
            level_expr = hl_data.get("Expression", {}).get("Level", {})
            if isinstance(level_expr, dict) and "Expression" in level_expr and \
               isinstance(level_expr["Expression"], dict) and "SourceRef" in level_expr["Expression"] and \
               isinstance(level_expr["Expression"]["SourceRef"], dict):
                 table_name = level_expr["Expression"]["SourceRef"].get("Entity")
                 field_name = level_expr.get("Level") 
            elif "Name" in hl_data: 
                 field_name = hl_data.get("Name")
        if field_name:
            extracted_fields.add(normalize_field_reference(table_name, str(field_name)))
    return list(extracted_fields)

def extract_fields_from_visual_config(visual_config: Dict[str, Any], visual_level_filters_str: Optional[str]) -> List[str]:
    fields = set()
    if not isinstance(visual_config, dict): 
        return []
    if "projections" in visual_config and isinstance(visual_config["projections"], dict):
        for _, proj_list in visual_config["projections"].items():
            if isinstance(proj_list, list):
                for proj_item in proj_list:
                    if isinstance(proj_item, dict) and "queryRef" in proj_item:
                        query_ref = proj_item.get("queryRef")
                        if isinstance(query_ref, str):
                            fields.add(normalize_field_reference(None, query_ref))
    single_visual_conf = visual_config.get("singleVisual", {})
    if isinstance(single_visual_conf, dict):
        prototype_query = single_visual_conf.get("prototypeQuery", {})
        if isinstance(prototype_query, dict) and "Select" in prototype_query:
            fields.update(extract_fields_from_query_selects(prototype_query["Select"]))
        query_section = single_visual_conf.get("query", {})
        if isinstance(query_section, dict) and "selects" in query_section:
            fields.update(extract_fields_from_query_selects(query_section["selects"]))
        slicer_data_objects = single_visual_conf.get("objects", {}).get("data") 
        if not slicer_data_objects: 
            general_obj = single_visual_conf.get("vcObjects", {}).get("general")
            if isinstance(general_obj, list) and general_obj: 
                 slicer_data_objects = general_obj[0].get("properties",{}).get("filterDataSource",{}).get("target")
            elif isinstance(general_obj, dict): 
                 slicer_data_objects = general_obj.get("properties",{}).get("filterDataSource",{}).get("target")
        slicer_target_props = {} 
        if isinstance(slicer_data_objects, list) and slicer_data_objects: 
            slicer_target_props_container = slicer_data_objects[0].get("properties", {}).get("target", {})
            if isinstance(slicer_target_props_container, dict) and "target" in slicer_target_props_container:
                 slicer_target_props = slicer_target_props_container.get("target",{})
            else: 
                 slicer_target_props = slicer_target_props_container
        elif isinstance(slicer_data_objects, dict): 
            slicer_target_props = slicer_data_objects
        if isinstance(slicer_target_props, dict): 
            table = slicer_target_props.get("table")
            column = slicer_target_props.get("column")
            measure = slicer_target_props.get("measure")
            hierarchy = slicer_target_props.get("hierarchy")
            level = slicer_target_props.get("level") 
            if table and column: fields.add(normalize_field_reference(table, column))
            elif table and hierarchy and level: fields.add(normalize_field_reference(table, level))
            elif table and measure: fields.add(normalize_field_reference(table, measure))
            elif measure: fields.add(normalize_field_reference(None, measure)) 
    data_transforms = visual_config.get("dataTransforms", {})
    if isinstance(data_transforms, dict) and "selects" in data_transforms:
        for item in data_transforms.get("selects", []):
            if isinstance(item, dict):
                query_name = item.get("queryName")
                if query_name and isinstance(query_name, str) and ('.' in query_name or not any(c in query_name for c in '()[]{}')):
                    fields.add(normalize_field_reference(None, query_name))
                else:
                    expr = item.get("expr")
                    if isinstance(expr, dict):
                        fields.update(extract_fields_from_query_selects([expr])) 
                    elif item.get("displayName") and isinstance(item.get("displayName"), str):
                         fields.add(normalize_field_reference(None, item.get("displayName")))
    if visual_level_filters_str:
        try:
            filters_list = json.loads(visual_level_filters_str)
            if isinstance(filters_list, list):
                for filter_item in filters_list:
                    if isinstance(filter_item, dict):
                        target = filter_item.get("target")
                        if isinstance(target, list) and target: 
                             for t_item in target:
                                if isinstance(t_item, dict):
                                    table = t_item.get("table")
                                    column = t_item.get("column")
                                    measure = t_item.get("measure")
                                    hierarchy = t_item.get("hierarchy")
                                    level = t_item.get("level")
                                    if table and column: fields.add(normalize_field_reference(table, column))
                                    elif table and hierarchy and level: fields.add(normalize_field_reference(table, level))
                                    elif table and measure: fields.add(normalize_field_reference(table, measure))
                                    elif measure: fields.add(normalize_field_reference(None, measure))
                        expression = filter_item.get("expression")
                        if isinstance(expression, dict):
                             fields.update(extract_fields_from_query_selects([expression])) 
        except json.JSONDecodeError:
            print(f"Warning: Visual filters JSON decode error. String start: {visual_level_filters_str[:100]}...")
        except Exception as e:
            print(f"Warning: Error processing visual filters: {e}")
    return list(f for f in fields if f)

def parse_pbit_file(pbit_file_path: str) -> Optional[Dict[str, Any]]:
    extracted_metadata = {
        "tables": [], "relationships": [], "measures": {},
        "calculated_columns": {}, "report_pages": [],
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
                                col_name = col_data.get("name")
                                col_type = col_data.get("dataType")
                                columns.append({"name": col_name, "dataType": col_type})
                                if col_data.get("type") == "calculated" and "expression" in col_data:
                                    cc_key = normalize_field_reference(table_name, col_name)
                                    extracted_metadata["calculated_columns"][cc_key] = col_data["expression"]
                        extracted_metadata["tables"].append({"name": table_name, "columns": columns})
                if "tables" in model and isinstance(model["tables"], list): 
                    for table_data in model["tables"]:
                        if not isinstance(table_data, dict): continue
                        table_name = table_data.get("name")
                        if "measures" in table_data and isinstance(table_data["measures"], list):
                            for measure_data in table_data["measures"]:
                                if not isinstance(measure_data, dict): continue
                                measure_name = measure_data.get("name")
                                measure_expression = measure_data.get("expression")
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
            else:
                print(f"Warning: DataModelSchema content issue or 'model' key missing in {DATAMODEL_SCHEMA_PATH} after parsing attempts.")
            report_layout_json = safe_extract_json(pbit_zip, REPORT_LAYOUT_PATH)
            if report_layout_json and "sections" in report_layout_json and isinstance(report_layout_json["sections"], list): 
                for section in report_layout_json["sections"]:
                    if not isinstance(section, dict): continue
                    page_name = section.get("displayName")
                    visuals_on_page = []
                    if "visualContainers" in section and isinstance(section["visualContainers"], list):
                        for vc_idx, vc in enumerate(section["visualContainers"]):
                            if not isinstance(vc, dict): continue
                            try:
                                config_str = vc.get("config", "{}")
                                config = {} 
                                if isinstance(config_str, str) and config_str.strip():
                                    try:
                                        config = json.loads(config_str) 
                                    except json.JSONDecodeError as e_json_config:
                                        print(f"Warning: Inner visual config JSON decode error for page '{page_name}', visual index {vc_idx}: {e_json_config}. Config string (start): {config_str[:200]}")
                                        continue 
                                visual_type = None
                                if isinstance(config, dict): 
                                    visual_type = config.get("visualType") or \
                                                (config.get("singleVisual", {}).get("visualType") if isinstance(config.get("singleVisual"), dict) else None)
                                if not visual_type:
                                    visual_type = vc.get("name") 
                                visual_title = None
                                if isinstance(config, dict) and isinstance(config.get("singleVisual"), dict) and \
                                   isinstance(config["singleVisual"].get("vcObjects"), dict) and \
                                   isinstance(config["singleVisual"]["vcObjects"].get("title"), list) and \
                                   config["singleVisual"]["vcObjects"]["title"]:
                                    title_obj_list = config["singleVisual"]["vcObjects"]["title"]
                                    if title_obj_list and isinstance(title_obj_list[0], dict):
                                        title_props = title_obj_list[0].get("properties", {}).get("text", {})
                                        if isinstance(title_props, dict) and "expr" in title_props and \
                                           isinstance(title_props["expr"], dict) and "Literal" in title_props["expr"] and \
                                           isinstance(title_props["expr"]["Literal"], dict) and "Value" in title_props["expr"]["Literal"]:
                                            literal_val = title_props["expr"]["Literal"].get("Value")
                                            if isinstance(literal_val, str):
                                                visual_title = literal_val.strip("'")
                                visual_filters_str = vc.get("filters")
                                fields_used = extract_fields_from_visual_config(config, visual_filters_str)
                                visuals_on_page.append({
                                    "type": visual_type, "title": visual_title,
                                    "fields_used": list(set(fields_used)) 
                                })
                            except Exception as e_vc: 
                                print(f"Warning: Could not parse visual container on page '{page_name}', visual index {vc_idx}: {e_vc}")
                    extracted_metadata["report_pages"].append({
                        "name": page_name, "visuals": visuals_on_page
                    })
            else:
                print(f"Warning: Report/Layout content issue or 'sections' key missing in {REPORT_LAYOUT_PATH} after parsing attempts.")
        return extracted_metadata
    except FileNotFoundError:
        print(f"Error: PBIT file not found at {pbit_file_path}")
    except zipfile.BadZipFile:
        print(f"Error: Bad PBIT file (not a valid zip archive): {pbit_file_path}")
    except Exception as e:
        import traceback
        print(f"An unexpected error occurred during PBIT parsing: {e}")
        traceback.print_exc()
    return None

if __name__ == '__main__':
    dummy_pbit_path = "dummy_test_visuals_utf16le_no_bom.pbit" # New name for this test
    
    if not os.path.exists(dummy_pbit_path):
        print(f"Creating dummy PBIT: {dummy_pbit_path} for testing UTF-16 LE without BOM...")
        temp_dir_for_dummy = "dummy_pbit_contents_utf16le"
        os.makedirs(temp_dir_for_dummy, exist_ok=True)
        report_dir = os.path.join(temp_dir_for_dummy, "Report") 
        os.makedirs(report_dir, exist_ok=True)

        # DataModelSchema: UTF-16 LE without BOM
        dummy_datamodel_content_dict = {
            "name": "dummy-model-utf16le", "compatibilityLevel": 1550,
            "model": {"culture": "en-US", "tables": [
                {"name": "Sales", "columns": [{"name": "Amount", "dataType": "decimal"}],
                 "measures": [{"name": "Total Sales", "expression": "SUM(Sales[Amount])"}]},
                {"name": "Product", "columns": [{"name": "Category", "dataType": "string"}]}
            ]}
        }
        datamodel_json_str = json.dumps(dummy_datamodel_content_dict)
        with open(os.path.join(temp_dir_for_dummy, DATAMODEL_SCHEMA_PATH), 'wb') as f: 
            f.write(datamodel_json_str.encode('utf-16-le')) # Encode as UTF-16 LE, no explicit BOM written by encode()

        # Report/Layout: UTF-16 LE without BOM
        dummy_report_layout_content = {
            "sections": [{
                "displayName": "Overview_UTF16",
                "visualContainers": [{
                    "config": json.dumps({ 
                        "visualType": "card", "singleVisual": {"prototypeQuery": {"Select": [
                            {"Measure": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Total Sales"}}
                        ]}}
                    }), "filters": "[]" 
                },{
                    "config": json.dumps({
                        "visualType": "slicer", "singleVisual": {"objects": {"data": [{"properties": {"target": {"target": {"table": "Product", "column": "Category"}}}}]}}
                    }), "filters": "[]"
                }]
            }]
        }
        report_layout_json_str = json.dumps(dummy_report_layout_content)
        with open(os.path.join(report_dir, "Layout"), 'wb') as f: 
             f.write(report_layout_json_str.encode('utf-16-le'))
        
        archive_name = dummy_pbit_path.replace(".pbit", "")
        shutil.make_archive(archive_name, 'zip', root_dir=temp_dir_for_dummy, base_dir='.')
        if os.path.exists(dummy_pbit_path): os.remove(dummy_pbit_path)
        os.rename(archive_name + ".zip", dummy_pbit_path)
        print(f"Created dummy PBIT: {dummy_pbit_path}")
        if os.path.exists(temp_dir_for_dummy): shutil.rmtree(temp_dir_for_dummy)
    
    print(f"\nParsing {dummy_pbit_path}...")
    metadata = parse_pbit_file(dummy_pbit_path) 
    if metadata:
        print("\n--- Extracted Metadata (UTF-16 LE Test) ---")
        print(f"File: {metadata.get('file_name')}")
        print(f"Tables: {[t.get('name') for t in metadata.get('tables', [])]}")
        print(f"Measures: {list(metadata.get('measures', {}).keys())}")
        for page in metadata.get("report_pages", []):
            print(f"\nPage: {page['name']}")
            for visual in page.get("visuals", []):
                print(f"  - Visual Type: {visual['type']}, Title: {visual.get('title', 'N/A')}, Fields: {visual['fields_used']}")
    else:
        print("Metadata parsing failed or returned None.")