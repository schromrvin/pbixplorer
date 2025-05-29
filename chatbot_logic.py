import google.generativeai as genai
import pandas as pd
from typing import Dict, Any, List, Optional
import json

# --- Gemini Model Holder ---
gemini_model = None
MAX_SAMPLE_ROWS_PER_TABLE_IN_PROMPT = 10
MAX_TOTAL_SAMPLE_CHARS_IN_PROMPT = 12000 # Max chars for ALL table samples combined
MAX_TOOL_FETCHED_ROWS_FOR_REPROMPT = 200 # Max rows per table in a re-prompt
MAX_CHAT_HISTORY_TURNS = 3 # Number of user/assistant turn pairs in history

def configure_gemini_model(api_key: str):
    """Configures and returns the Gemini Pro model."""
    global gemini_model
    try:
        genai.configure(api_key=api_key)
        # Using gemini-2.5-flash-preview-05-20 for a balance of capability and speed/cost
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        gemini_model = model
        print("Gemini model configured successfully with 'gemini-2.5-flash-preview-05-20'.")
        return True
    except Exception as e:
        print(f"Error configuring Gemini model: {e}")
        gemini_model = None
        return False

def _format_table_sample_for_gemini(df_sample: pd.DataFrame, table_name: str) -> str:
    """Converts a DataFrame sample to a Markdown table string for Gemini."""
    if df_sample.empty:
        return f"  (No sample data available for table '{table_name}' or table is empty)\n"
    try:
        # Using .to_markdown() for better formatting if tabulate is available, else to_string()
        try:
            # Ensure tabulate is installed: pip install tabulate
            md_table = df_sample.to_markdown(index=False)
            return f"  Sample Data for '{table_name}' (first {len(df_sample)} rows):\n{md_table}\n\n"
        except ImportError:
            # Fallback if tabulate is not installed
            return f"  Sample Data for '{table_name}' (first {len(df_sample)} rows):\n  ```text\n{df_sample.to_string(index=False, max_rows=MAX_SAMPLE_ROWS_PER_TABLE_IN_PROMPT)}\n  ```\n"
    except Exception:
        return f"  (Error formatting sample data for table '{table_name}')\n"

def _format_tables_schema_for_gemini(metadata_source: Any, file_type: str, pbix_object_for_samples: Optional[Any]) -> str:
    context_parts = []
    total_sample_chars_added = 0

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
                else: context_parts.append("  (No columns listed)")
                context_parts.append("  (Data samples are primarily available for PBIX files in this view)\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'schema'):
        schema_df = metadata_source.schema
        if schema_df is not None and not schema_df.empty:
            context_parts.append("=== Data Model Schema (Tables & Columns with Data Samples) ===")
            all_pbix_tables = sorted(list(schema_df['TableName'].unique()))
            for table_name in all_pbix_tables:
                context_parts.append(f"\n--- Table: {table_name} ---")
                table_cols_df = schema_df[schema_df['TableName'] == table_name]
                if not table_cols_df.empty:
                    context_parts.append("Columns:")
                    for _, row in table_cols_df.iterrows():
                        context_parts.append(f"  - {row['ColumnName']} (DataType: {row['PandasDataType']})")
                else:
                    context_parts.append("  (No columns listed in schema DataFrame)")

                if pbix_object_for_samples and total_sample_chars_added < MAX_TOTAL_SAMPLE_CHARS_IN_PROMPT:
                    try:
                        df_sample = pbix_object_for_samples.get_table(table_name).head(MAX_SAMPLE_ROWS_PER_TABLE_IN_PROMPT)
                        sample_str = _format_table_sample_for_gemini(df_sample, table_name)
                        if total_sample_chars_added + len(sample_str) <= MAX_TOTAL_SAMPLE_CHARS_IN_PROMPT:
                            context_parts.append(sample_str)
                            total_sample_chars_added += len(sample_str)
                        else:
                            context_parts.append(f"  (Sample data display limit for initial prompt reached before table '{table_name}')\n")
                            break # Stop adding more samples if limit is hit
                    except Exception:
                        context_parts.append(f"  (Note: Could not fetch/format sample data for '{table_name}')\n")
                elif total_sample_chars_added >= MAX_TOTAL_SAMPLE_CHARS_IN_PROMPT:
                     context_parts.append(f"  (Sample data display limit for initial prompt reached before table '{table_name}')\n")
            context_parts.append("\n")
    return "\n".join(context_parts)

def _format_dax_constructs_for_gemini(metadata_source: Any, file_type: str) -> str:
    context_parts = []
    # Measures
    if file_type == "pbit" and isinstance(metadata_source, dict):
        measures = metadata_source.get("measures", {})
        if measures:
            context_parts.append("=== DAX Measures ===")
            for name, formula in sorted(measures.items()): context_parts.append(f"- `{name}` := ```dax\n{formula}\n```")
            context_parts.append("\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'dax_measures'):
        measures_df = metadata_source.dax_measures
        if measures_df is not None and not measures_df.empty:
            context_parts.append("=== DAX Measures ===")
            for _, row in measures_df.iterrows():
                desc = f" (Description: {row['Description']})" if pd.notna(row['Description']) and row['Description'] else ""
                folder = f" (Display Folder: {row['DisplayFolder']})" if pd.notna(row['DisplayFolder']) and row['DisplayFolder'] else ""
                context_parts.append(f"- `{row['TableName']}.{row['Name']}`{desc}{folder} := ```dax\n{row['Expression']}\n```")
            context_parts.append("\n")
    # Calculated Columns
    if file_type == "pbit" and isinstance(metadata_source, dict):
        ccs = metadata_source.get("calculated_columns", {})
        if ccs:
            context_parts.append("=== DAX Calculated Columns ===")
            for name, formula in sorted(ccs.items()): context_parts.append(f"- `{name}` := ```dax\n{formula}\n```")
            context_parts.append("\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'dax_columns'):
        ccs_df = metadata_source.dax_columns
        if ccs_df is not None and not ccs_df.empty:
            context_parts.append("=== DAX Calculated Columns ===")
            for _, row in ccs_df.iterrows(): context_parts.append(f"- `{row['TableName']}.{row['ColumnName']}` := ```dax\n{row['Expression']}\n```")
            context_parts.append("\n")
    return "\n".join(context_parts)

def _format_relationships_for_gemini(metadata_source: Any, file_type: str) -> str:
    context_parts = []
    if file_type == "pbit" and isinstance(metadata_source, dict):
        relationships = metadata_source.get("relationships", [])
        if relationships:
            context_parts.append("=== Relationships ===")
            for rel in relationships: context_parts.append(f"- From `{rel.get('fromTable','?')}.{rel.get('fromColumn','?')}` To `{rel.get('toTable','?')}.{rel.get('toColumn','?')}` (Active: {rel.get('isActive', True)}, Filter: {rel.get('crossFilteringBehavior', 'N/A')})")
            context_parts.append("\n")
    elif file_type == "pbix" and hasattr(metadata_source, 'relationships'):
        rels_df = metadata_source.relationships
        if rels_df is not None and not rels_df.empty:
            context_parts.append("=== Relationships ===")
            for _, row in rels_df.iterrows(): context_parts.append(f"- From `{row['FromTableName']}.{row['FromColumnName']}` To `{row['ToTableName']}.{row['ToColumnName']}` (Active: {row['IsActive']}, Card: {row['Cardinality']}, Filter: {row['CrossFilteringBehavior']})")
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
                analysis = mq.get('analysis', {}); sources = analysis.get('sources', []); transforms = analysis.get('transformations', [])
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
    if report_layout_data:
        context_parts.append("=== Report Structure (Pages & Visuals) ===")
        for page in report_layout_data:
            page_name = page.get("name", "Unknown Page"); visuals = page.get("visuals", [])
            context_parts.append(f"\n-- Page: {page_name} ({len(visuals)} visuals) --")
            if visuals:
                for visual in visuals:
                    title = visual.get('title', 'Untitled Visual'); v_type = visual.get('type', 'N/A'); fields = visual.get('fields_used', [])
                    fields_str = f", Fields Used: `{', '.join(fields)}`" if fields else ""
                    context_parts.append(f"  - Title: \"{title}\", Type: \"{v_type}\"{fields_str}")
            else: context_parts.append("  (No visuals listed)")
        context_parts.append("\n")
    return "\n".join(context_parts)

def format_chat_history_for_prompt(chat_history: List[Dict[str, str]], max_turns: int = MAX_CHAT_HISTORY_TURNS) -> str:
    if not chat_history:
        return ""
    formatted_history = []
    start_index = max(0, len(chat_history) - (max_turns * 2))
    for message in chat_history[start_index:]:
        role = "User" if message["role"] == "user" else "PBIXpert"
        formatted_history.append(f"{role}: {message['content']}")
    if not formatted_history:
        return ""
    return "\n\nPrevious Conversation (for context):\n" + "\n".join(formatted_history) + "\n\n"

def format_metadata_for_gemini(primary_metadata: Any, file_type: str,
                               original_file_name: str,
                               pbix_report_layout: Optional[List[Dict[str, Any]]] = None) -> str:
    context_parts = [
        f"== Power BI File Analysis Context ==",
        f"File Name: {original_file_name}",
        f"File Type: {file_type.upper()}\n"
    ]
    pbix_samples_obj = primary_metadata if file_type == "pbix" else None
    context_parts.append(_format_tables_schema_for_gemini(primary_metadata, file_type, pbix_samples_obj))
    context_parts.append(_format_dax_constructs_for_gemini(primary_metadata, file_type))
    context_parts.append(_format_relationships_for_gemini(primary_metadata, file_type))
    context_parts.append(_format_m_queries_for_gemini(primary_metadata, file_type))
    report_data_source = None
    if file_type == "pbit" and isinstance(primary_metadata, dict):
        report_data_source = primary_metadata.get("report_pages")
    elif file_type == "pbix" and pbix_report_layout:
        report_data_source = pbix_report_layout
    if report_data_source:
        context_parts.append(_format_report_structure_for_gemini(report_data_source))
    context_parts.append("== End of Initial Context ==")
    return "\n".join(filter(None, context_parts))

def generate_gemini_response(full_prompt: str) -> str:
    global gemini_model
    if not gemini_model:
        return "Error: Gemini model is not configured."
    try:
        # print(f"--- PROMPT SENT TO GEMINI (length: {len(full_prompt)}) ---\n{full_prompt[:2000]}...\n--- END OF PROMPT ---") # For debugging
        response = gemini_model.generate_content(full_prompt)
        # print(f"--- GEMINI RESPONSE RECEIVED ---\n{response.text[:2000]}...\n--- END OF RESPONSE ---") # For debugging
        if response.parts:
            return response.text
        else:
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                 block_reason = response.prompt_feedback.block_reason
                 if block_reason: return f"Error: The response was blocked. Reason: {block_reason}."
            return "Error: Empty or unexpected response from AI model."
    except Exception as e:
        # print(f"Exception during Gemini API call: {e}") # For debugging
        return f"Error during Gemini API call: {e}"

def construct_initial_prompt(user_query: str, metadata_context_string: str, chat_history_string: str) -> str:
    return f"""You are PBIXpert, an expert Power BI data analyst assistant.
Your goal is to provide insightful analysis based on the provided Power BI file context and conversation history.

{chat_history_string}

Context Includes: File name, type, table schemas with SMALL DATA SAMPLES for PBIX tables (first {MAX_SAMPLE_ROWS_PER_TABLE_IN_PROMPT} rows, total chars capped), DAX, relationships, M queries, and report structure if available.

Your Capabilities & Behavior:
1.  **Direct Analysis & Calculation:** When asked for analysis (e.g., "total sales by month", "average price per product"), USE THE PROVIDED DATA SAMPLES (initial or fetched via tool) to PERFORM the calculations and PRESENT THE RESULTS directly. Do not just suggest DAX or steps for the user to perform. Clearly state which data/tables your analysis is based on. If DAX measures exist that achieve the user's goal, you can cite and explain them, but also try to compute a result if sample data is relevant.
2.  **Metadata Interpretation:** Answer questions about the file's structure. Interpret DAX and M code.
3.  **Tool Use for More Data (Mandatory if Samples are Insufficient):**
    *   The initial data samples are small. If a user's query requires analyzing more data than available in these initial samples for an accurate answer, you MUST request the necessary full table(s).
    *   To request data, output the following JSON block on its own lines. You can request MULTIPLE tables at once. NOTHING ELSE before or after the JSON block in your response if making a tool request.
        // TOOL_REQUEST_START
        {{
          "tool_name": "fetch_tables_for_analysis",
          "parameters": {{
            "table_names": ["TableName1", "TableName2_if_needed"],
            "reason_for_user": "To accurately [perform your query task, e.g., 'analyze yearly sales trends'], I need to analyze more records from the 'TableName1' (and 'TableName2') table(s)."
          }}
        }}
        // TOOL_REQUEST_END
4.  **Handling Insufficient Data (Even After Fetch):** If, even after fetching table data (which will be a sample of {MAX_TOOL_FETCHED_ROWS_FOR_REPROMPT} rows per table), the information is still insufficient for the precise query (e.g., data for requested year is missing, or not enough detail), explain this limitation clearly.
5.  **General Knowledge & Predictions:** Answer general data/business questions. For predictions, state they are speculative based on available context and general knowledge, requiring more comprehensive data for reliability.
6.  **Formatting & Clarity:** Use Markdown for all responses (headings, lists, bold, code blocks for DAX/M). Be clear if info isn't in context. Use qualified names for DAX items like `'Table Name'[Measure Name]` or `TableName[Column Name]`.

Power BI File Metadata Context:
{metadata_context_string}

Current User Query: {user_query}
PBIXpert:
"""

def construct_reprompt_with_fetched_data(user_query: str, metadata_context_string: str, chat_history_string: str,
                                         fetched_table_names: List[str], fetched_data_summary_string: str) -> str:
    return f"""You are PBIXpert. You previously requested more data for the table(s): {', '.join(fetched_table_names)} to answer the user's query.
That data has now been fetched (a sample of up to {MAX_TOOL_FETCHED_ROWS_FOR_REPROMPT} rows per table is provided below).
Please PERFORM THE ANALYSIS using this additional data along with the original full metadata context and conversation history to answer the original user query. Present the computed results and insights directly.

{chat_history_string}

Original Power BI File Metadata Context (includes initial small samples for all tables):
{metadata_context_string}

Additional Fetched Data for Table(s) '{', '.join(fetched_table_names)}' (up to {MAX_TOOL_FETCHED_ROWS_FOR_REPROMPT} rows per table):
{fetched_data_summary_string}

Original User Query: {user_query}
PBIXpert:
"""