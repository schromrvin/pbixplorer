import streamlit as st
import os
import tempfile
from pbit_parser import parse_pbit_file
from chatbot_logic import process_query

# --- Page Configuration ---
st.set_page_config(page_title="PBIT Metadata Chatbot", layout="wide")

# --- Session State Initialization ---
if "pbit_metadata" not in st.session_state:
    st.session_state.pbit_metadata = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = None

# --- UI Elements ---
st.title("Power BI Template (.pbit) Metadata Chatbot 🤖")
st.caption("Upload a .pbit file to analyze its metadata. Ask questions about tables, columns, measures, relationships, and report structure.")

# --- File Upload and Processing ---
uploaded_file = st.file_uploader("Choose a .pbit file", type=["pbit"])

if uploaded_file is not None:
    # Check if it's a new file or the same one
    if st.session_state.uploaded_file_name != uploaded_file.name:
        st.session_state.chat_history = [] # Reset chat for new file
        st.session_state.uploaded_file_name = uploaded_file.name
        
        with st.spinner(f"Processing '{uploaded_file.name}'... This may take a moment."):
            # Save to a temporary file to pass its path to the parser
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pbit") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_file_path = tmp_file.name
            
            try:
                metadata = parse_pbit_file(temp_file_path)
                st.session_state.pbit_metadata = metadata
                if metadata:
                    st.success(f"Successfully parsed '{uploaded_file.name}'!")
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": f"I've analyzed '{metadata.get('file_name', 'your file')}'. What would you like to know about it?"}
                    )
                else:
                    st.error("Could not parse the PBIT file. Check console for warnings/errors from the parser.")
                    st.session_state.pbit_metadata = None # Ensure it's reset on error
            except Exception as e:
                st.error(f"An error occurred during processing: {e}")
                st.session_state.pbit_metadata = None
            finally:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path) # Clean up the temporary file

# --- Chat Interface ---
if st.session_state.pbit_metadata:
    st.header(f"Chat about: {st.session_state.pbit_metadata.get('file_name', 'Loaded PBIT')}")

    # Display chat messages from history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    if prompt := st.chat_input("Ask a question about the PBIT file..."):
        # Add user message to chat history
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = process_query(prompt, st.session_state.pbit_metadata)
            st.markdown(response)
        
        # Add assistant response to chat history
        st.session_state.chat_history.append({"role": "assistant", "content": response})
else:
    if uploaded_file is None:
        st.info("Please upload a .pbit file to begin.")
    # If upload failed or file was unparsable, a message is already shown.

# --- Sidebar with some general info or help ---
st.sidebar.header("About")
st.sidebar.info(
    "This app helps you understand the metadata within Power BI Template (.pbit) files. "
    "It does not query live data or connect to any services. "
    "All processing is done locally in your browser (via Streamlit server)."
)
st.sidebar.markdown("---")
st.sidebar.subheader("Example Questions:")
st.sidebar.markdown("""
- List tables
- Describe table 'Sales'
- What columns in 'Products'
- List measures
- What is the formula for measure 'Sales.Total Sales'
- Show DAX for measure 'Average Price'
- List calculated columns
- List relationships
- List pages
- What visuals are on page 'Overview'
- Where is column 'Sales.ProductID' used?
- Which visuals use measure 'Total Revenue'?
""")