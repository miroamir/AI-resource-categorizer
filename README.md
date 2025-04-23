# 🎧 AI Resource Categorizer – 

This is a production-ready Python script that transcribes, analyzes, and intelligently tags video, audio, PDF, and HTML resources using AI.

It powers dynamic classification for Trailblaze — an educational platform with thousands of diverse content types. The script uses Deepgram for transcription and Gemini (Google) for smart tagging, with fallback logic, structured transcript storage, and full database integration via SQLAlchemy.

---

## 🚀 What It Does

- 🔍 Scans video/audio resources (MP4, YouTube, etc.)
- 🧠 Transcribes content using Deepgram’s Nova-3 model
- 🤖 Classifies content using Gemini (Google AI) based on predefined tags
- 📄 Parses PDFs and HTML with fallback JS-loaded video detection (via Selenium)
- 🗂️ Saves structured transcripts and AI-generated tags to PostgreSQL via SQLAlchemy

---

## 🧠 Powered By

- Python 3.10
- Deepgram Nova-3
- Gemini 2.0 Flash (via `google-generativeai`)
- SQLAlchemy (PostgreSQL ORM)
- yt_dlp, BeautifulSoup, Selenium
- dotenv, PyPDF2, asyncio

---

## 📂 Project Structure

trailblaze-ai-resource-analyzer/ ├── analyzer.py # Main script ├── requirements.txt # Python dependencies ├── .env.example # Example env file ├── README.md # You're reading it



---

## 🔧 Environment Setup

Create a `.env` file in your root directory using this template:

```env
DEEPGRAM_API_KEY=your_deepgram_api_key
GEMINI_API_KEY=your_gemini_api_key
POSTGRES_URL=postgresql://user:pass@localhost/dbname


▶️ How to Run
Install dependencies:

pip install -r requirements.txt

Then run the script inside your app context:

python analyzer.py
Make sure your Flask app and database models are correctly set up in app.py.


⚠️ Disclaimer
This is a production-grade module built as part of a larger system.
It assumes a pre-configured PostgreSQL database and Flask app context with models: Resource, Transcript, Tag, and TagsResources.
