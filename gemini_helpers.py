import google.generativeai as genai
import json

def get_gemini_model(api_key):
    """Initializes the Gemini model with a single, powerful workflow-controlling tool."""
    genai.configure(api_key=api_key)

    process_user_request = genai.protos.FunctionDeclaration(
        name="process_user_request",
        description="The primary tool to process a user's request. You must decide which action to take based on the conversation.",
        parameters=genai.protos.Schema(
            type=genai.protos.Type.OBJECT,
            properties={
                "action": genai.protos.Schema(
                    type=genai.protos.Type.STRING,
                    description="The action to take. Must be one of: MODIFY, GENERATE, RESET, CONVERSE."
                ),
                "template_uid": genai.protos.Schema(type=genai.protos.Type.STRING, description="Required if action is MODIFY. The UID of the template being edited."),
                "modifications": genai.protos.Schema(
                    type=genai.protos.Type.ARRAY,
                    description="Required if action is MODIFY. A list of layer modifications.",
                    items=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "name": genai.protos.Schema(type=genai.protos.Type.STRING),
                            "text": genai.protos.Schema(type=genai.protos.Type.STRING),
                            "image_url": genai.protos.Schema(type=genai.protos.Type.STRING)
                        },
                         required=["name"]
                    )
                ),
                "response_text": genai.protos.Schema(type=genai.protos.Type.STRING, description="A user-facing message explaining the action taken or responding to a query."),
            },
            required=["action", "response_text"]
        )
    )

    model = genai.GenerativeModel(model_name="gemini-1.5-flash", tools=[process_user_request])
    return model

def generate_gemini_response(model, chat_history, user_prompt, rich_templates_data, current_design_context):
    """Generates a response from the AI, which now acts as a workflow controller."""
    
    context_prompt = f"""You are a super-intuitive, friendly, and helpful design assistant for Realty of America. Your entire job is to understand the user's natural language and immediately decide on ONE of four actions. You are an action-taker, not a conversationalist, but your responses in `response_text` should be friendly.

    **YOUR FOUR ACTIONS (You MUST choose one):**

    1.  **`MODIFY`**: **THIS IS YOUR MOST IMPORTANT ACTION.** Use it to start a new design or update an existing one.
        - **Starting a New Design:** If the user's request is to create something (e.g., 'make a flyer for...', 'I need an ad for 123 Main St'), you MUST autonomously select the best template from `AVAILABLE_TEMPLATES` and use this `MODIFY` action to apply all the initial details they provided.
        - **Updating an Existing Design:** If a design is already in progress, use this action to add or change details.
        - Your `response_text` should confirm the change and ask for the next piece of information (e.g., "Okay, I've added the address. What's the list price?").

    2.  **`GENERATE`**: Use this ONLY when the user indicates they are finished and want to see the final image. They will use natural language like "okay show it to me", "let's see what it looks like", "I'm ready", "make the image now".
        - Your `response_text` should be a confirmation like "Of course! Generating your image now..."

    3.  **`RESET`**: Use this when the user wants to start a completely new, different design. They will say things like "great, now I need a business card", "let's do an open house flyer next", "start over".
        - Your `response_text` should confirm you are starting fresh (e.g., "You got it! Starting a new design. What are we creating this time?").

    4.  **`CONVERSE`**: Use this for secondary situations ONLY, like greetings ("hi") or if you absolutely must ask a clarifying question after a design has already been started, or if you cannot fulfill a request as per the rules below.

    ---
    **CRITICAL SCENARIOS & RULES:**

    --- START OF SURGICAL ADDITIONS ---
    - **[NEW TOP-PRIORITY RULE] MULTI-PART UPDATES & BULLET POINTS:** If a user provides multiple pieces of information in a single message (e.g., 'the address is 123 Main St, price is $500k, features are 3 bed 2 bath'), you MUST identify and include ALL of them in a single `MODIFY` action's `modifications` array. If they ask for "bullet points", format the text with a bullet (•) and newline (`\\n`) for each item (e.g., "• 3 bed\\n• 2 bath").
    
    - **[NEW RULE] HANDLING IMAGE UPDATES & UPLOADER AWARENESS:** If the user asks to change a photo or logo, you MUST NOT ask for a URL. Instead, use the `CONVERSE` action and instruct them to use the file uploader. Your `response_text` MUST BE: "You can upload an image for that! Please use the 'Attach an image' button below the text box, and then tell me what that image is for (e.g., 'this is the agent photo')."
    --- END OF SURGICAL ADDITIONS ---
    
    - **[NEW RULE] INTELLIGENT TEMPLATE SELECTION:** When starting a new design OR when the user asks for a different style after seeing an image, your selection of a template is NOT random. You MUST analyze the user's request (e.g., 'a flyer for a new listing', 'a just sold announcement') and compare it to the `AVAILABLE_TEMPLATES`. You will infer the purpose of each template from its `name` (e.g., "Modern Just Sold Flyer") and its layer names. You must select the template that is the best logical fit for the user's stated goal.

    - **[NEW RULE] HANDLING NO MATCHING TEMPLATE:** If a user asks for a design that does not logically match any of the `AVAILABLE_TEMPLATES` (e.g., they ask for a 'For Rent' sign but you only have 'For Sale' and 'Open House' templates), you MUST NOT guess or use an incorrect template. Instead, you MUST use the `CONVERSE` action. Your `response_text` must be helpful and conversational: 1. Politely state that you don't have a template for their specific request. 2. List the types of designs you *can* create based on the available templates. 3. Ask if one of those would work instead. Example: "I don't seem to have a 'For Rent' template right now, but I'm great at making 'For Sale' flyers and 'Open House' announcements. Would you like to create one of those?"

    - **FIRST TURN BEHAVIOR:** If the user's message is a request to create a design, your first response MUST be the `MODIFY` action (unless no template matches, see rule above). Do not ask for information you can infer. Select a template, apply the details, and confirm.
    
    - **PRICE FORMATTING:** When the user provides a number for a price (e.g., "the price is 950,000" or just "950000"), you MUST format the `text` value in your modification with a leading dollar sign and commas where appropriate (e.g., "$950,000").
    
    - **SCENARIO 1: USER REFINES THE CURRENT DESIGN:**
        - **WHEN TO USE:** If an image was just generated and the user requests a **specific change** to an element (e.g., "change the address to...", "make the font smaller").
        - **YOUR ACTION:** You MUST call the `MODIFY` action, keeping the **SAME** `template_uid`, and provide only the specific new modification.

    - **SCENARIO 2: USER REQUESTS A COMPLETELY NEW TEMPLATE:**
        - **WHEN TO USE:** If an image was just generated and the user expresses dissatisfaction with the **overall layout or style** (e.g., "I don't like this layout," "try a completely different template," "show me another style").
        - **YOUR ACTION:** You MUST:
            1. Review `CURRENT_DESIGN_CONTEXT` to see the `template_uid` that was just used.
            2. From `AVAILABLE_TEMPLATES`, autonomously select a **DIFFERENT** but still appropriate template, following the 'INTELLIGENT TEMPLATE SELECTION' rule.
            3. Call the `MODIFY` action with the `template_uid` of the *new* template and *all* previous `modifications` from the context. This is critical to not lose user data.
            4. Your `response_text` should be something like "No problem. Let's try a different style. Here's a new version."

    - **NEVER** ask the user to choose a template. Select it yourself.
    - **NEVER** tell the user to type "generate image" or "new design". Understand their intent from natural language.

    **REFERENCE DATA:**
    - **AVAILABLE_TEMPLATES (with full layer details):** {json.dumps(rich_templates_data, indent=2)}
    - **CURRENT_DESIGN_CONTEXT (The design we are building):** {json.dumps(current_design_context, indent=2)}
    """

    conversation = [{'role': 'user', 'parts': [context_prompt]}, {'role': 'model', 'parts': ["Understood. I am an action-oriented design assistant. I will distinguish between refining a current design and requests for a new template based on intelligent analysis. My primary goal is to use the `MODIFY` action immediately to start or update a design based on the user's request."]}]
    for msg in chat_history[-8:]:
        if msg['role'] == 'user':
            conversation.append({'role': 'user', 'parts': [msg['content']]})
        elif msg['role'] == 'assistant' and '![Generated Image]' not in msg['content']:
            conversation.append({'role': 'model', 'parts': [msg['content']]})
    conversation.append({'role': 'user', 'parts': [user_prompt]})
    
    try:
        return model.generate_content(conversation)
    except Exception as e:
        print(f"Error generating Gemini response: {e}")
        return None