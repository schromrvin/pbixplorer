import google.generativeai as genai
import pandas as pd
from typing import Dict, Any, List, Optional

# --- Gemini Model Holder ---
# This allows initializing the model once with the API key.
# You might want to move API key configuration to app.py for better UI.
gemini_model = None

def configure_gemini_model(api_key: str):
    """Configures and returns the Gemini Pro model."""
    global gemini_model
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest') # Or 'gemini-pro'
        # Test with a simple generation to ensure connectivity
        # model.generate_content("test") # Disabled for now to avoid eager calls during setup
        gemini_model = model
        print("Gemini model configured successfully.")
        return True
    except Exception as e:
        print(f"Error configuring Gemini model: {e}")
        gemini_model = None
        return False

def _format_tables_schema_for_gemini(metadata_source: Any, file_type: str) -> str:
    context_parts = []
    if file_type == "pbit" and isinstance(metadata_source, dict):
        tables = metadata_source.get("tables", [])
        if tables:
            context_parts.append("=== Data Model Schema (Tables & Columns) ===")
            for table in tables:
                table_name = table.get("name", "Unknown Table")
                context_parts.append(f"\n--- Table: {table_name} ---")
                columns = table.get("columns", [])
                if columns:
                    context_parts.append("Columns:")
                    for col in columns:
                        context_parts.append(f"  - {col.get('name', '?')} (DataType: {col.get('dataType', '?')})")
                else:
                    context_parts.append("  (No columns listed)")
            context_parts.append("\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'schema'): # PBIXRay object
        schema_df = metadata_source.schema
        if schema_df is not None and not schema_df.empty:
            context_parts.append("=== Data Model Schema (Tables & Columns) ===")
            for table_name in sorted(list(schema_df['TableName'].unique())):
                context_parts.append(f"\n--- Table: {table_name} ---")
                table_cols_df = schema_df[schema_df['TableName'] == table_name]
                if not table_cols_df.empty:
                    context_parts.append("Columns:")
                    for _, row in table_cols_df.iterrows():
                        # PBIXRay's schema_df also has Cardinality, IsNullable from ColumnStorage/DictionaryStorage
                        # We can add these if available and useful
                        # Example: card_info = f", Cardinality: {row['Cardinality']}" if 'Cardinality' in row and pd.notna(row['Cardinality']) else ""
                        context_parts.append(f"  - {row['ColumnName']} (DataType: {row['PandasDataType']})") # Add Cardinality later if needed
                else:
                    context_parts.append("  (No columns listed in schema DataFrame)")
            context_parts.append("\n")
    return "\n".join(context_parts)

def _format_dax_constructs_for_gemini(metadata_source: Any, file_type: str) -> str:
    context_parts = []
    # Measures
    if file_type == "pbit" and isinstance(metadata_source, dict):
        measures = metadata_source.get("measures", {})
        if measures:
            context_parts.append("=== DAX Measures ===")
            for name, formula in sorted(measures.items()):
                context_parts.append(f"- {name} := {formula}")
            context_parts.append("\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'dax_measures'):
        measures_df = metadata_source.dax_measures
        if measures_df is not None and not measures_df.empty:
            context_parts.append("=== DAX Measures ===")
            for _, row in measures_df.iterrows():
                desc = f" (Description: {row['Description']})" if pd.notna(row['Description']) and row['Description'] else ""
                folder = f" (Display Folder: {row['DisplayFolder']})" if pd.notna(row['DisplayFolder']) and row['DisplayFolder'] else ""
                context_parts.append(f"- {row['TableName']}.{row['Name']} := {row['Expression']}{desc}{folder}")
            context_parts.append("\n")

    # Calculated Columns
    if file_type == "pbit" and isinstance(metadata_source, dict):
        ccs = metadata_source.get("calculated_columns", {})
        if ccs:
            context_parts.append("=== DAX Calculated Columns ===")
            for name, formula in sorted(ccs.items()):
                context_parts.append(f"- {name} := {formula}")
            context_parts.append("\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'dax_columns'):
        ccs_df = metadata_source.dax_columns
        if ccs_df is not None and not ccs_df.empty:
            context_parts.append("=== DAX Calculated Columns ===")
            for _, row in ccs_df.iterrows():
                context_parts.append(f"- {row['TableName']}.{row['ColumnName']} := {row['Expression']}")
            context_parts.append("\n")
    return "\n".join(context_parts)

def _format_relationships_for_gemini(metadata_source: Any, file_type: str) -> str:
    context_parts = []
    if file_type == "pbit" and isinstance(metadata_source, dict):
        relationships = metadata_source.get("relationships", [])
        if relationships:
            context_parts.append("=== Relationships ===")
            for rel in relationships:
                context_parts.append(f"- From '{rel.get('fromTable','?')}.{rel.get('fromColumn','?')}' To '{rel.get('toTable','?')}.{rel.get('toColumn','?')}' (Active: {rel.get('isActive', True)}, Filter: {rel.get('crossFilteringBehavior', 'N/A')})")
            context_parts.append("\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'relationships'):
        rels_df = metadata_source.relationships
        if rels_df is not None and not rels_df.empty:
            context_parts.append("=== Relationships ===")
            for _, row in rels_df.iterrows():
                context_parts.append(f"- From '{row['FromTableName']}.{row['FromColumnName']}' To '{row['ToTableName']}.{row['ToColumnName']}' (Active: {row['IsActive']}, Card: {row['Cardinality']}, Filter: {row['CrossFilteringBehavior']})")
            context_parts.append("\n")
    return "\n".join(context_parts)

def _format_m_queries_for_gemini(metadata_source: Any, file_type: str) -> str:
    context_parts = []
    if file_type == "pbit" and isinstance(metadata_source, dict):
        m_queries = metadata_source.get("m_queries", [])
        if m_queries:
            context_parts.append("=== M Queries (Power Query) ===")
            for mq in m_queries:
                context_parts.append(f"-- Table: {mq.get('table_name', '?')} --")
                analysis = mq.get('analysis', {})
                sources = analysis.get('sources', [])
                transforms = analysis.get('transformations', [])
                if sources: context_parts.append(f"  Sources: {', '.join(sources)}")
                if transforms: context_parts.append(f"  Transformations: {', '.join(transforms)}")
                context_parts.append(f"Script:\n```m\n{mq.get('script', 'N/A')}\n```")
            context_parts.append("\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'power_query'):
        pq_df = metadata_source.power_query
        if pq_df is not None and not pq_df.empty:
            context_parts.append("=== M Queries (Power Query) ===")
            for _, row in pq_df.iterrows():
                context_parts.append(f"-- Table: {row['TableName']} --")
                context_parts.append(f"Script:\n```m\n{row['Expression']}\n```")
            context_parts.append("\n")
    return "\n".join(context_parts)

def _format_report_structure_for_gemini(report_layout_data: Optional[List[Dict[str, Any]]]) -> str:
    context_parts = []
    if report_layout_data: # This is a list of page dicts
        context_parts.append("=== Report Structure (Pages & Visuals) ===")
        for page in report_layout_data:
            page_name = page.get("name", "Unknown Page")
            visuals = page.get("visuals", [])
            context_parts.append(f"\n-- Page: {page_name} ({len(visuals)} visuals) --")
            if visuals:
                for visual in visuals:
                    title = visual.get('title', 'Untitled Visual')
                    v_type = visual.get('type', 'N/A')
                    fields = visual.get('fields_used', [])
                    fields_str = f", Fields Used: {', '.join(fields)}" if fields else ""
                    context_parts.append(f"  - Title: \"{title}\", Type: \"{v_type}\"{fields_str}")
            else:
                context_parts.append("  (No visuals listed)")
        context_parts.append("\n")
    return "\n".join(context_parts)


def format_metadata_for_gemini(primary_metadata: Any, file_type: str,
                               original_file_name: str,
                               pbix_report_layout: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Serializes all extracted PBIT/PBIX metadata into a single string for Gemini prompt.
    """
    context_parts = [
        f"== Power BI File Analysis Context ==",
        f"File Name: {original_file_name}",
        f"File Type: {file_type.upper()}\n"
    ]

    context_parts.append(_format_tables_schema_for_gemini(primary_metadata, file_type))
    context_parts.append(_format_dax_constructs_for_gemini(primary_metadata, file_type))
    context_parts.append(_format_relationships_for_gemini(primary_metadata, file_type))
    context_parts.append(_format_m_queries_for_gemini(primary_metadata, file_type))

    if file_type == "pbit" and isinstance(primary_metadata, dict):
        context_parts.append(_format_report_structure_for_gemini(primary_metadata.get("report_pages")))
    elif file_type == "pbix" and pbix_report_layout:
        context_parts.append(_format_report_structure_for_gemini(pbix_report_layout))

    context_parts.append("== End of Context ==")
    return "\n".join(filter(None, context_parts)) # Filter out empty strings from parts


def process_query_with_gemini(user_query: str,
                              primary_metadata: Any,
                              file_type: str,
                              original_file_name: str,
                              pbix_report_layout: Optional[List[Dict[str, Any]]] = None) -> str:
    global gemini_model
    if not gemini_model:
        return "Error: Gemini model is not configured. Please set the API key in the sidebar."

    # 1. Prepare the context
    metadata_context_string = format_metadata_for_gemini(
        primary_metadata, file_type, original_file_name, pbix_report_layout
    )

    # 2. Construct the prompt
    system_prompt = f"""You are an expert Power BI data analyst and assistant named "PBIXpert".
Your task is to analyze the provided Power BI file metadata context and answer user questions comprehensively.
The context includes information about tables, columns, data types, DAX measures, calculated columns, relationships, M (Power Query) scripts, and potentially report structure (pages and visuals).

Capabilities:
- Answer questions about the file's structure (tables, columns, measures, relationships, M queries, report layout).
- Interpret DAX and M code if present in the context.
- Perform data analysis based *only* on the provided metadata and any explicit data summaries in the context. For example, you can count items, list distinct values if they are part of a small cardinality column visible in the schema, or describe relationships.
- If a question requires analyzing actual row-level data from a table (e.g., "What is the total sales for Product X?", "Show me all records for January"), and only the schema/metadata is provided for that table in the context, you MUST state that you need the actual data from the specific table(s) to answer accurately. You can suggest the user inspect the table using the application's features if available. DO NOT attempt to invent or hallucinate data values.
- You can answer general questions related to data concepts, Power BI, DAX, M, business terminology, or external factors if they are relevant to the user's query or the domain suggested by the data context.
- If asked for predictions (e.g., future sales), clearly state that any prediction is speculative, based on the limited metadata context (if any relevant trend is discernible) and general knowledge, and that actual data analysis would be required for a reliable forecast.

Constraints & Behavior:
- Primarily focus your answers on the provided Power BI file context.
- If information is not available in the context, state that clearly (e.g., "The provided context does not contain information about X.").
- Format your responses using Markdown for readability (e.g., use headings, bullet points, bold text, code blocks for DAX/M).
- Be helpful, detailed, and aim to provide actionable insights where possible based on the metadata.
- When referring to DAX measures or calculated columns, use their fully qualified names (e.g., 'TableName'[MeasureName] or TableName[ColumnName]).
- If you are using specific parts of the context to answer, you can subtly refer to them, e.g., "Based on the schema for the 'Sales' table..."

The Power BI file metadata context is as follows:
{metadata_context_string}

Now, please answer the following user query.
User Query: {user_query}
Assistant Response (PBIXpert):
"""

    # 3. Call Gemini API
    try:
        # print("--- Sending Prompt to Gemini ---") # For debugging
        # print(system_prompt[:2000] + "...") # Print a snippet of the prompt
        # print("--- End of Prompt Snippet ---")

        # Gemini API expects a list of Content parts for its generate_content method
        # For simple text-only, it's just one part.
        response = gemini_model.generate_content(system_prompt)
        
        # print("--- Gemini Raw Response ---") # For debugging
        # try:
        #     print(response.text)
        # except Exception as e_text:
        #     print(f"Error accessing response.text: {e_text}")
        #     print(f"Full response object: {response}")
        # print("--- End of Gemini Raw Response ---")

        if response.parts:
            return response.text
        else:
            # Handle cases where the response might be blocked or empty
            # Check response.prompt_feedback for blockages
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                 block_reason = response.prompt_feedback.block_reason
                 if block_reason:
                     return f"Error: The response was blocked by the API. Reason: {block_reason}. Please try rephrasing your query or check the content policies."
            return "Error: Received an empty or unexpected response from the AI model."

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        # import traceback # For debugging
        # print(traceback.format_exc()) # For debugging
        return f"Sorry, an error occurred while processing your request with the AI model: {e}"