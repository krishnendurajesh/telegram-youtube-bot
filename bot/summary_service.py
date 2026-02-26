import httpx
import json
from bot.config import OPENCLAW_BASE_URL, OPENCLAW_MODEL

async def call_model(prompt: str, temperature: float = 0.3):
    """
    Streams response from the Ollama model.
    Yields chunks of text as they arrive.
    """
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{OPENCLAW_BASE_URL}/api/generate",
                json={
                    "model": OPENCLAW_MODEL,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": temperature,
                        "num_predict": 250,  # Balanced length
                        "num_ctx": 1024,     # Standard context for stability
                        "top_k": 40,
                        "top_p": 0.9
                    }
                }
            ) as response:
                if response.status_code != 200:
                    yield f"Model error: {response.status_code}"
                    return

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    except Exception as e:
        yield f"Error: {str(e)}"

async def generate_summary(transcript: str, language: str = "English"):
    # Restored to 800 characters for better quality
    transcript_snippet = transcript[:800]

    headers = {
        "Hindi": {"title": "शीर्षक", "overview": "अवलोकन", "insights": "मुख्य अंतर्दृष्टि", "takeaway": "मुख्य निष्कर्ष"},
        "Malayalam": {"title": "ശീർഷകം", "overview": "അവലോകനം", "insights": "പ്രധാന ഉൾക്കാഴ്ചകൾ", "takeaway": "പ്രധാന പാഠം"},
        "Tamil": {"title": "தலைப்பு", "overview": "மேலோட்டம்", "insights": "முக்கிய நுண்ணறிவு", "takeaway": "முக்கிய கருத்து"},
        "Telugu": {"title": "శీర్షిక", "overview": "అవలోకనం", "insights": "ముఖ్యమైన అంతర్దృష్టులు", "takeaway": "ప్రధానాంశం"},
        "Spanish": {"title": "Título", "overview": "Resumen", "insights": "Información clave", "takeaway": "Conclusión principal"},
        "French": {"title": "Titre", "overview": "Aperçu", "insights": "Points clés", "takeaway": "Conclusion principale"},
        "German": {"title": "Titel", "overview": "Überblick", "insights": "Wichtige Erkenntnisse", "takeaway": "Kernaussage"},
    }

    h = headers.get(language, {"title": "Title", "overview": "Overview", "insights": "Key Insights", "takeaway": "Core Takeaway"})

    language_constraint = ""
    if language != "English":
        language_constraint = "DO NOT use a single word of English.\nDO NOT use English headers."

    prompt = f"""
INSTRUCTION: You are a professional summarizer.
The source transcript may be in a different language than the target output {language}. 
Your task is to analyze the source and provide a structured summary strictly in {language}.

CRITICAL: The entire response MUST be written ONLY in {language}. 
{language_constraint}

{h['title']}:

{h['overview']}:

{h['insights']}:
- {h['insights']} 1
- {h['insights']} 2
- {h['insights']} 3
- {h['insights']} 4
- {h['insights']} 5
- {h['insights']} 6

{h['takeaway']}:

Transcript:
{transcript_snippet}
"""
    async for chunk in call_model(prompt, temperature=0.1):
        yield chunk

def retrieve_relevant_chunk(transcript: str, question: str, chunk_size: int = 200):
    transcript = transcript.lower()
    question = question.lower()
    chunks = [transcript[i:i+chunk_size] for i in range(0, len(transcript), chunk_size)]
    question_words = set(question.split())
    best_score = -1
    best_chunk = chunks[0] if chunks else ""
    for chunk in chunks:
        chunk_words = set(chunk.split())
        score = len(question_words.intersection(chunk_words))
        if score > best_score:
            best_score = score
            best_chunk = chunk
    return best_chunk

async def generate_answer(transcript: str, question: str, history: list, language: str = "English"):
    relevant_chunk = retrieve_relevant_chunk(transcript, question, chunk_size=200)
    
    conversation_context = ""
    for turn in history[-2:]:
        conversation_context += f"{turn['role']}: {turn['content']}\n"

    not_covered_msg = {
        "Hindi": "यह विषय वीडियो में शामिल नहीं है।",
        "Malayalam": "ഈ വിഷയം വീഡിയോയിൽ ഉൾപ്പെടുത്തിയിട്ടില്ല.",
        "Tamil": "இந்தத் தலைப்பு வீடியோவில் இடம்பெறவில்லை.",
        "Telugu": "ఈ అంశం వీడియోలో లేదు.",
        "Spanish": "Este tema no está cubierto en el video.",
        "French": "Ce sujet n'est pas abordé dans la vidéo.",
        "German": "Dieses Thema wird im Video nicht behandelt.",
    }.get(language, "This topic is not covered in the video.")

    prompt = f"""
CRITICAL: Reply ONLY in {language}.
Answer the following question based ONLY on the transcript excerpt provided. 

Previous Conversation:
{conversation_context}

Transcript Excerpt:
{relevant_chunk}

Question:
{question}
"""
    async for chunk in call_model(prompt, temperature=0.2):
        yield chunk

async def generate_deepdive(transcript: str, language: str = "English"):
    prompt = f"""
CRITICAL: Reply ONLY in {language}.
Provide an in-depth analytical summary of the following transcript.
- Explain major arguments clearly.
- Discuss implications.
- Maximum 400 words.

Transcript: {transcript[:800]}
"""
    async for chunk in call_model(prompt, temperature=0.4):
        yield chunk

async def generate_action_points(transcript: str, language: str = "English"):
    prompt = f"""
CRITICAL: Reply ONLY in {language}.
Extract 6-10 clear and concise practical action points.

Transcript: {transcript[:800]}
"""
    async for chunk in call_model(prompt, temperature=0.3):
        yield chunk
