import os
import textwrap
import json
import re
import streamlit as st
import requests
from datetime import date, datetime

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Background image
PEXELS_BG = "https://images.pexels.com/photos/414171/pexels-photo-414171.jpeg"

# API Key
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Set background
def set_background_from_url(img_url: str):
    css = f"""
    <style>
    .stApp {{
        background-image: url('{img_url}');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}
    .block-container {{
        background: rgba(255,255,255,0.8);
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# Prompt template
WEATHER_PROMPT_TEMPLATE = textwrap.dedent("""\
You are a weather reporter. Use the provided real-time weather data to create a human-friendly forecast.
Respond only in JSON with the schema:

{{
  "location": "{city}",
  "date": "{date}",
  "summary": "<summary>",
  "temperature": {{
    "low_c": <float>,
    "high_c": <float>,
    "feels_like_c": <float>
  }},
  "condition": "<condition>",
  "details": "<narrative>",
  "advice": "<tip>",
  "confidence": "high"
}}

Rules:
- Always include the "location" field exactly as provided unless a more precise location is found.
- Never return text before or after the JSON.
- Use only the provided weather data below.

Weather data (JSON):
{weather_data}

Tone: {tone}
""")

# Fetch weather data
def fetch_realtime_weather(city):
    if not OPENWEATHER_API_KEY:
        raise RuntimeError("OPENWEATHER_API_KEY not set")
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise RuntimeError(f"Weather API error: {resp.text}")
    data = resp.json()
    data['location'] = city
    return data

# Extract JSON safely
def extract_json(text: str) -> str:
    cleaned = text.strip()

    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[\s\S]*\}', cleaned)
    if match:
        candidate = match.group(0).strip()
        json.loads(candidate)  # verify parse
        return candidate

    raise ValueError("No valid JSON found in AI response.")

# AI weather report
def get_ai_weather_report_ollama(city, date_str, tone="friendly"):
    weather_data = fetch_realtime_weather(city)

    prompt = WEATHER_PROMPT_TEMPLATE.format(
        city=city,
        date=date_str,
        weather_data=json.dumps(weather_data),
        tone=tone
    )

    url = "http://localhost:11434/api/generate"
    payload = {"model": "llama3.2:1b", "prompt": prompt}

    resp = requests.post(url, json=payload, stream=True)
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama API error: {resp.text}")

    full_response = ""
    for chunk in resp.iter_lines(decode_unicode=True):
        if chunk:
            try:
                chunk_data = json.loads(chunk)
                full_response += chunk_data.get("response", "")
            except Exception:
                continue

    sanitized = re.sub(r'```json', '', full_response)
    sanitized = re.sub(r'```', '', sanitized).strip()
    return extract_json(sanitized)

# Main app
def main():
    st.set_page_config(page_title="AI Weather Simulator", page_icon="🌤️")
    set_background_from_url(PEXELS_BG)
    st.title("🌤️ AI-Powered Weather Simulator")
    st.caption("Real-time weather reports via Ollama LLM")

    with st.sidebar:
        tone = st.selectbox("Tone", ["friendly", "professional", "playful", "concise"], index=0)
        show_raw = st.checkbox("Show raw JSON output", value=False)

    city = st.text_input("City name", placeholder="e.g. Bengaluru, India")
    date_str = st.date_input("Forecast date", value=date.today())

    if st.button("Generate forecast"):
        if not city:
            st.warning("Please enter a city name.")
            return

        st.info("Generating weather report...")
        try:
            out = get_ai_weather_report_ollama(city, str(date_str), tone)

            if show_raw:
                st.code(out, language="json")

            try:
                parsed = json.loads(out)
                loc = parsed.get("location", city)
                forecast_date = parsed.get("date", str(date_str))

                st.subheader(f"Forecast — {loc} — {forecast_date}")
                st.markdown(f"**{parsed.get('summary', '')}**")

                t = parsed.get("temperature", {})
                cols = st.columns(3)
                cols[0].metric("Low (°C)", t.get("low_c", "—"))
                cols[1].metric("High (°C)", t.get("high_c", "—"))
                cols[2].metric("Feels like (°C)", t.get("feels_like_c", "—"))

                st.markdown(f"**Condition:** {parsed.get('condition', '—')}")
                st.write(parsed.get("details", ""))
                st.info(f"Tip: {parsed.get('advice', '')}")
                st.caption(f"Confidence: {parsed.get('confidence', '—')}")

            except json.JSONDecodeError:
                st.error("⚠ AI returned invalid JSON. Showing raw output below.")
                st.text_area("Raw AI Output", out, height=200)

        except Exception as e:
            st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
