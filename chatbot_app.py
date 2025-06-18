# Forcing a fresh deploy on Streamlit Cloud
import streamlit as st
import os
import requests
from dotenv import load_dotenv

from pathlib import Path

# Import helper modules
from bannerbear_helpers import get_template_details, create_image, poll_for_image
from gemini_helpers import get_gemini_model, generate_gemini_response
from image_uploader import upload_image_to_freeimage
from ui_helpers import inject_css, typing_indicator # <-- Import from ui_helpers

# --- 1. Page Configuration & Setup ---
st.set_page_config(page_title="ROA AI Designer", layout="centered")
inject_css() # <-- Inject custom CSS for the typing indicator

image_path = Path(__file__).parent / "roa.png"
st.image(str(image_path), width=200)
st.title("AI Design Assistant")
st.caption("Powered by Realty of America")

# --- API & State Initialization ---
load_dotenv()
BB_API_KEY, GEMINI_API_KEY = os.getenv("BANNERBEAR_API_KEY"), os.getenv("GEMINI_API_KEY")

@st.cache_resource(show_spinner="Loading design templates...")
def load_all_template_details():
    try:
        if not BB_API_KEY: return None
        summary_url = "https://api.bannerbear.com/v2/templates"
        headers = {"Authorization": f"Bearer {BB_API_KEY}"}
        response = requests.get(summary_url, headers=headers, timeout=15)
        response.raise_for_status()
        summary = response.json()
        return [get_template_details(BB_API_KEY, t['uid']) for t in summary if t]
    except Exception as e:
        st.error(f"Error loading templates: {e}", icon="🚨")
        return None

def initialize_session_state():
    defaults = {
        "messages": [{"role": "assistant", "content": "Hello! I'm your design assistant. Just tell me what you need to create."}],
        "gemini_model": get_gemini_model(GEMINI_API_KEY),
        "rich_templates_data": load_all_template_details(),
        "design_context": {"template_uid": None, "modifications": []},
        "staged_file": None
    }
    for key, default_value in defaults.items():
        if key not in st.session_state: st.session_state[key] = default_value

# --- Handler Functions ---
def handle_ai_decision(decision):
    """The central router that executes the AI's chosen action."""
    action = decision.get("action")
    response_text = decision.get("response_text", "I'm not sure how to proceed.")
    trigger_generation = False
    
    # --- The CONVERSE action just passes text through, so we can handle it here ---
    if action == "CONVERSE":
        return response_text

    # --- FIX: Major logic refactor for clarity and correctness ---

    # Step 1: Always update the context with any new info from the AI decision.
    # This ensures that modifications are never lost.
    if action == "MODIFY":
        # First, handle template assignment or change
        new_template_uid = decision.get("template_uid")
        if new_template_uid and new_template_uid != st.session_state.design_context.get("template_uid"):
            # If the template is swapped, we want to regenerate immediately after updating details.
            if st.session_state.design_context.get("template_uid") is not None:
                trigger_generation = True
            st.session_state.design_context["template_uid"] = new_template_uid

        # Next, merge modifications. This is the "upsert" logic.
        # It takes existing mods from the state and overlays the new ones from the AI.
        current_mods_dict = {mod['name']: mod for mod in st.session_state.design_context.get('modifications', [])}
        new_mods_from_ai = decision.get("modifications", [])
        for mod in new_mods_from_ai:
            current_mods_dict[mod['name']] = dict(mod)
        
        # The session state now holds the complete, up-to-date list of modifications.
        st.session_state.design_context["modifications"] = list(current_mods_dict.values())

    elif action == "GENERATE":
        trigger_generation = True

    elif action == "RESET":
        st.session_state.design_context = {"template_uid": None, "modifications": []}
        return response_text # Stop here for reset

    # Step 2: If generation was triggered (either by "generate" or template swap), run it now.
    # This block now uses the fully updated session state as the single source of truth.
    if trigger_generation:
        context = st.session_state.design_context
        if not context.get("template_uid"):
            return "I can't generate an image yet. Please describe the design you want first."
        
        with st.spinner("Generating your image... This may take a moment."):
            # IMPORTANT: We use the now-updated list of modifications from the session state.
            final_modifications = context.get("modifications", [])
            initial_response = create_image(BB_API_KEY, context['template_uid'], final_modifications)
            
            if not initial_response:
                response_text = "❌ **Error:** Failed to start image generation."
            else:
                final_image = poll_for_image(BB_API_KEY, initial_response)
                if final_image and final_image.get("image_url_png"):
                    response_text += f"\n\n![Generated Image]({final_image['image_url_png']})"
                else:
                    response_text = "❌ **Error:** Image generation failed during rendering."

    return response_text

# --- Main App Execution ---
initialize_session_state()

if not st.session_state.rich_templates_data:
    st.error("Application cannot start because design templates could not be loaded. Please ensure your BANNERBEAR_API_KEY is correct and restart.", icon="🛑")
    st.stop()

# --- START OF CHANGE: Moved file uploader to sidebar ---
with st.sidebar:
    st.header("Upload Image")
    staged_file_bytes = st.file_uploader("Attach an image to your next message", type=["png", "jpg", "jpeg"])
    if staged_file_bytes:
        st.session_state.staged_file = staged_file_bytes.getvalue()
        st.success("✅ Image attached and ready!")
# --- END OF CHANGE ---

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)

# Chat input logic
if prompt := st.chat_input("Your message..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        placeholder = st.empty()
        # Use the typing indicator instead of static text
        placeholder.markdown(typing_indicator(), unsafe_allow_html=True)
        
        final_prompt_for_ai = prompt
        if st.session_state.staged_file:
            with st.spinner("Uploading your image..."):
                image_url = upload_image_to_freeimage(st.session_state.staged_file) 
                st.session_state.staged_file = None
                if image_url:
                    final_prompt_for_ai = f"Image context: The user has just uploaded an image, available at {image_url}. Their text command is: '{prompt}'"
                else:
                    placeholder.error("Image upload failed.", icon="❌")
                    final_prompt_for_ai = None

        response_text = "I'm sorry, something went wrong. Could you please try rephrasing?"
        if final_prompt_for_ai:
            response = generate_gemini_response(
                model=st.session_state.gemini_model,
                chat_history=st.session_state.messages,
                user_prompt=final_prompt_for_ai,
                rich_templates_data=st.session_state.rich_templates_data,
                current_design_context=st.session_state.design_context
            )
            
            # --- START OF FIX: More robust response handling ---
            if response and response.candidates:
                part = response.candidates[0].content.parts[0]
                # Case 1: The AI returned a function call (the primary workflow).
                if hasattr(part, 'function_call') and part.function_call:
                    decision = dict(part.function_call.args)
                    response_text = handle_ai_decision(decision)
                # Case 2: The AI returned a direct text response for conversation.
                elif hasattr(part, 'text') and part.text:
                    response_text = part.text
                # Case 3: The response was malformed or empty.
                else:
                    response_text = "I'm having trouble connecting right now. Please try again in a moment."
            # Case 4: The API call itself failed or returned no candidates.
            else:
                response_text = "I'm having trouble connecting right now. Please try again in a moment."
            # --- END OF FIX ---

        placeholder.markdown(response_text, unsafe_allow_html=True)
    st.session_state.messages.append({"role": "assistant", "content": response_text})