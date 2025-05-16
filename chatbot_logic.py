from typing import Dict, Any, List, Optional

def find_entity(text: str, entities: List[str]) -> Optional[str]:
    """Finds the first matching entity in the text (case-insensitive)."""
    text_lower = text.lower()
    for entity in entities:
        if entity.lower() in text_lower: # Simple substring check
            return entity
    return None

def find_entities_in_query(text: str, entity_list: List[str]) -> List[str]:
    """Finds all occurrences of entities from entity_list in text (case-insensitive)."""
    found_entities = []
    text_lower = text.lower()
    for entity_name in entity_list:
        if entity_name.lower() in text_lower:
            found_entities.append(entity_name)
    return found_entities

def get_all_table_names(metadata: Dict[str, Any]) -> List[str]:
    return [table['name'] for table in metadata.get('tables', []) if table.get('name')]

def get_all_measure_names_qualified(metadata: Dict[str, Any]) -> List[str]:
    return list(metadata.get('measures', {}).keys())

def get_all_cc_names_qualified(metadata: Dict[str, Any]) -> List[str]:
    return list(metadata.get('calculated_columns', {}).keys())

def get_simple_names_from_qualified(qualified_names: List[str]) -> List[str]:
    return list(set(name.split('.')[-1] for name in qualified_names if name))

def get_all_column_names_from_tables_qualified(metadata: Dict[str, Any]) -> List[str]:
    qualified_cols = []
    for table in metadata.get('tables', []):
        table_name = table.get('name')
        if table_name:
            for col in table.get('columns', []):
                col_name = col.get('name')
                if col_name:
                    qualified_cols.append(f"{table_name}.{col_name}")
    return list(set(qualified_cols))

def get_all_page_names(metadata: Dict[str, Any]) -> List[str]:
    return [page['name'] for page in metadata.get('report_pages', []) if page.get('name')]


def process_query(query: str, metadata: Dict[str, Any]) -> str:
    query_lower = query.lower()

    table_names = get_all_table_names(metadata)
    
    qualified_measure_names = get_all_measure_names_qualified(metadata)
    simple_measure_names = get_simple_names_from_qualified(qualified_measure_names)
    
    qualified_cc_names = get_all_cc_names_qualified(metadata)
    simple_cc_names = get_simple_names_from_qualified(qualified_cc_names)
    
    qualified_table_column_names = get_all_column_names_from_tables_qualified(metadata)
    simple_table_column_names = get_simple_names_from_qualified(qualified_table_column_names)

    # All known qualified field names (measures, CCs, regular columns)
    all_known_qualified_fields = list(set(qualified_measure_names + qualified_cc_names + qualified_table_column_names))
    # All known simple field names
    all_known_simple_fields = list(set(simple_measure_names + simple_cc_names + simple_table_column_names))

    page_names = get_all_page_names(metadata)

    # --- Intent: List all tables ---
    if "list tables" in query_lower or "show tables" in query_lower:
        if table_names:
            return "Tables in this PBIT file:\n" + "\n".join([f"- {name}" for name in table_names])
        return "No table information found in the PBIT file."

    # --- Intent: Describe a table (list columns) ---
    if "describe table" in query_lower or "what columns in" in query_lower or "show columns for" in query_lower:
        table_name_match = find_entity(query, table_names)
        if table_name_match:
            for table in metadata.get("tables", []):
                if table.get("name","").lower() == table_name_match.lower():
                    cols = [f"- {c.get('name','N/A')} ({c.get('dataType','N/A')})" for c in table.get("columns",[])]
                    if not cols: return f"Table '{table_name_match}' has no columns defined or they could not be parsed."
                    return f"Columns in table '{table_name_match}':\n" + "\n".join(cols)
            return f"Table '{table_name_match}' not found."
        return "Which table are you asking about? Example: 'describe table Sales'"

    # --- Intent: List all measures ---
    if "list measures" in query_lower or "show measures" in query_lower:
        if qualified_measure_names:
            return "Measures in this PBIT file (format: Table.MeasureName or MeasureName if global):\n" + "\n".join([f"- {name}" for name in qualified_measure_names])
        return "No measures found in the PBIT file."

    # --- Intent: Get DAX formula for a measure ---
    if "what is the formula for" in query_lower or "show dax for" in query_lower or "formula of measure" in query_lower:
        target_measure_key = find_entity(query, qualified_measure_names)
        
        if not target_measure_key:
            simple_measure_match = find_entity(query, simple_measure_names)
            if simple_measure_match:
                possible_keys = [k for k in qualified_measure_names if k.lower().endswith(f".{simple_measure_match.lower()}") or k.lower() == simple_measure_match.lower()]
                if len(possible_keys) == 1:
                    target_measure_key = possible_keys[0]
                elif len(possible_keys) > 1:
                    return f"Measure '{simple_measure_match}' is ambiguous. Found as: {', '.join(possible_keys)}. Please specify fully (e.g., 'formula for TableName.{simple_measure_match}')."
        
        if target_measure_key and target_measure_key in metadata.get("measures", {}):
            return f"DAX formula for measure '{target_measure_key}':\n{metadata['measures'][target_measure_key]}"
        
        if find_entity(query, simple_measure_names + qualified_measure_names): # If any measure-like term was in query
             return f"Measure not found or its formula is not available. Please be specific (e.g. 'Table.MeasureName' or 'MeasureName' if unique)."
        return "Which measure are you asking about? Example: 'formula for Total Sales' or 'formula for Sales.Total Sales'"
    
    # --- Intent: List all calculated columns ---
    if "list calculated columns" in query_lower or "show calculated columns" in query_lower:
        if qualified_cc_names:
            return "Calculated Columns (format: Table.ColumnName):\n" + "\n".join([f"- {name}: {metadata['calculated_columns'][name]}" for name in qualified_cc_names])
        return "No calculated columns found."

    # --- Intent: Get DAX for a calculated column ---
    if "formula for calculated column" in query_lower or "dax for column" in query_lower:
        target_cc_key = find_entity(query, qualified_cc_names)
        
        if not target_cc_key:
            simple_cc_match = find_entity(query, simple_cc_names)
            if simple_cc_match:
                possible_keys = [k for k in qualified_cc_names if k.lower().endswith(f".{simple_cc_match.lower()}")]
                if len(possible_keys) == 1:
                    target_cc_key = possible_keys[0]
                elif len(possible_keys) > 1:
                    return f"Calculated column '{simple_cc_match}' is ambiguous. Found as: {', '.join(possible_keys)}. Please specify fully (e.g., 'formula for calculated column TableName.{simple_cc_match}')."

        if target_cc_key and target_cc_key in metadata.get('calculated_columns', {}):
            return f"DAX for calculated column '{target_cc_key}':\n{metadata['calculated_columns'][target_cc_key]}"
        
        if find_entity(query, simple_cc_names + qualified_cc_names):
            return f"Calculated column not found or its formula is not available. Please specify as 'TableName.ColumnName'."
        return "Which calculated column? (e.g., 'formula for calculated column Sales.Profit')"

    # --- Intent: List relationships ---
    if "list relationships" in query_lower or "show relationships" in query_lower:
        relationships = metadata.get("relationships", [])
        if relationships:
            rels = [
                f"- From {r.get('fromTable','?')}.{r.get('fromColumn','?')} To {r.get('toTable','?')}.{r.get('toColumn','?')} (Active: {r.get('isActive', 'N/A')}, Filter: {r.get('crossFilteringBehavior', 'N/A')})"
                for r in relationships
            ]
            return "Relationships:\n" + "\n".join(rels)
        return "No relationships found."

    # --- Intent: List pages ---
    if "list pages" in query_lower or "show pages" in query_lower:
        if page_names:
            return "Report Pages:\n" + "\n".join([f"- {name}" for name in page_names])
        return "No report pages found."
    
    # --- Intent: List visuals on a page ---
    if "visuals on page" in query_lower or "what visuals are on" in query_lower:
        page_name_match = find_entity(query, page_names)
        if page_name_match:
            for page in metadata.get("report_pages", []):
                if page.get("name","").lower() == page_name_match.lower():
                    visuals = page.get("visuals", [])
                    if visuals:
                        vis_info = [f"  - Type: {v.get('type','N/A')}, Title: {v.get('title', 'N/A')}, Fields: {', '.join(v.get('fields_used',[])) if v.get('fields_used') else 'N/A'}" for v in visuals]
                        return f"Visuals on page '{page_name_match}':\n" + "\n".join(vis_info)
                    return f"No visuals found on page '{page_name_match}'."
            return f"Page '{page_name_match}' not found."
        return "Which page are you asking about? Example: 'visuals on page Sales Overview'"

    # --- Intent: Where is a field (column/measure) used in visuals? ---
    if "where is column" in query_lower or "where is measure" in query_lower or \
       "visuals use field" in query_lower or "which visuals use" in query_lower:
        
        searched_field_qualified = find_entity(query, all_known_qualified_fields)
        searched_field_simple = None
        if not searched_field_qualified:
            searched_field_simple = find_entity(query, all_known_simple_fields)

        field_to_search_final_lower = None
        search_term_display = None

        if searched_field_qualified:
            field_to_search_final_lower = searched_field_qualified.lower()
            search_term_display = searched_field_qualified
        elif searched_field_simple:
            possible_qualified_matches = [
                qf for qf in all_known_qualified_fields 
                if qf.lower().endswith(f".{searched_field_simple.lower()}") or qf.lower() == searched_field_simple.lower()
            ]
            if len(possible_qualified_matches) == 1:
                field_to_search_final_lower = possible_qualified_matches[0].lower()
                search_term_display = possible_qualified_matches[0]
            elif len(possible_qualified_matches) > 1:
                return (f"Field '{searched_field_simple}' is ambiguous. It could refer to: "
                        f"{', '.join(possible_qualified_matches)}. Please be more specific (e.g., 'TableName.{searched_field_simple}').")
            else: # Simple name in query, but no unique mapping to a qualified field
                field_to_search_final_lower = searched_field_simple.lower()
                search_term_display = searched_field_simple
        
        if not field_to_search_final_lower:
            return "Which column or measure are you asking about? Example: 'where is column Sales.Amount used?' or 'which visuals use measure Total Sales?'"

        results = []
        for page in metadata.get("report_pages", []):
            for visual in page.get("visuals", []):
                for field_in_visual_parsed in visual.get("fields_used", []):
                    field_in_visual_lower = field_in_visual_parsed.lower()
                    
                    # Match conditions:
                    # 1. Direct match of search term (qualified or simple) with visual field (qualified or simple)
                    # 2. Search term is simple, visual field is qualified and ends with simple term
                    # 3. Search term is qualified, visual field is simple and is the last part of qualified term
                    if field_to_search_final_lower == field_in_visual_lower or \
                       (not '.' in field_to_search_final_lower and field_in_visual_lower.endswith(f".{field_to_search_final_lower}")) or \
                       ('.' in field_to_search_final_lower and field_to_search_final_lower.endswith(f".{field_in_visual_lower}")):
                        
                        visual_identifier = f"'{visual.get('title', visual.get('type', 'Unknown type'))}' on page '{page.get('name','Unknown Page')}'"
                        found_text = f"- Field '{search_term_display}' (found as '{field_in_visual_parsed}') is used in visual {visual_identifier}."
                        if found_text not in results:
                             results.append(found_text)

        if results:
            return f"Usage of field '{search_term_display}':\n" + "\n".join(results)
        return f"Field '{search_term_display}' not found in any visuals using that specific term, or the visual parsing couldn't identify it. The parser extracts fields as 'Table.Column' or 'MeasureName'."

    # --- Fallback ---
    return (
        "Sorry, I didn't understand that. Try asking things like:\n"
        "- List tables\n"
        "- Describe table 'Table Name'\n"
        "- List measures\n"
        "- Formula for measure 'Measure Name' or 'Table.Measure Name'\n"
        "- List calculated columns\n"
        "- Formula for calculated column 'Table.Column'\n"
        "- List relationships\n"
        "- List pages\n"
        "- Visuals on page 'Page Name'\n"
        "- Where is column 'Table.Column' used\n"
        "- Which visuals use measure 'Measure Name'"
    )

if __name__ == '__main__':
    # Dummy metadata for testing chatbot_logic.py
    dummy_metadata = {
        "file_name": "test.pbit",
        "tables": [
            {"name": "Sales", "columns": [
                {"name": "OrderID", "dataType": "int64"}, {"name": "Amount", "dataType": "decimal"},
                {"name": "ProductKey", "dataType": "int64"}, {"name": "CustomerKey", "dataType": "string"}
            ]},
            {"name": "Product", "columns": [
                {"name": "ProductKey", "dataType": "int64"}, {"name": "ProductName", "dataType": "string"},
                {"name": "Category", "dataType": "string"}
            ]},
            {"name": "Customer", "columns": [{"name": "CustomerKey", "dataType": "string"}, {"name": "CustomerName", "dataType": "string"}]}
        ],
        "measures": {
            "Sales.Total Sales": "SUM(Sales[Amount])",
            "Product.Avg Price": "AVERAGE(Product[Price])" # Assuming a Price column for example
        },
        "calculated_columns": {
            "Sales.IsHighValue": "IF(Sales[Amount] > 1000, TRUE, FALSE)",
            "Product.Full Name": "Product[ProductName] & \" (\" & Product[Category] & \")\""
        },
        "relationships": [
            {"fromTable": "Sales", "fromColumn": "ProductKey", "toTable": "Product", "toColumn": "ProductKey", "crossFilteringBehavior": "Both"},
            {"fromTable": "Sales", "fromColumn": "CustomerKey", "toTable": "Customer", "toColumn": "CustomerKey"}
        ],
        "report_pages": [
            {
                "name": "Sales Overview",
                "visuals": [
                    {"type": "card", "title": "Total Sales Card", "fields_used": ["Sales.Total Sales"]},
                    {"type": "table", "title": "Sales Details Table", "fields_used": ["Sales.OrderID", "Product.ProductName", "Sales.Amount"]},
                    {"type": "slicer", "title": "Product Category Slicer", "fields_used": ["Product.Category"]}
                ]
            },
            { "name": "Product Details", "visuals": [ {"type": "bar chart", "title": "Sales by Product", "fields_used": ["Product.ProductName", "Sales.Total Sales"]}]}
        ]
    }

    queries = [
        "list tables",
        "describe table Product",
        "list measures",
        "formula for measure Sales.Total Sales",
        "formula for measure Avg Price", # simple measure name
        "list calculated columns",
        "formula for calculated column Product.Full Name",
        "dax for column IsHighValue", # simple cc name
        "list relationships",
        "list pages",
        "visuals on page Sales Overview",
        "where is column Product.Category used", # qualified column
        "which visuals use Category", # simple column name
        "where is measure Sales.Total Sales used", # qualified measure
        "which visuals use Total Sales", # simple measure name
        "where is column Sales.OrderID used",
        "hello there" # Fallback
    ]

    print("--- Chatbot Logic Test ---")
    for q_idx, q in enumerate(queries):
        print(f"\n--- Query {q_idx+1} ---")
        print(f"USER: {q}")
        response = process_query(q, dummy_metadata)
        print(f"BOT: {response}")