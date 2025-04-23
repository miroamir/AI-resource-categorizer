import os
import re
import json
import uuid
import mimetypes
import logging
import requests
import subprocess
import PyPDF2
import yt_dlp
from bs4 import BeautifulSoup
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv
from app import db, Tag, Resource, TagsResources, Transcript
from google import genai
import asyncio
from deepgram import DeepgramClient




# Load .env variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Init Gemini AI
gemini = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options={"api_version": "v1alpha"},
)

# Init Deepgram with API key from environment
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise EnvironmentError("DEEPGRAM_API_KEY not found in environment variables or .env file")



deepgram = DeepgramClient(DEEPGRAM_API_KEY)

# Path to chromedriver
CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"


def transcribe_audio(video_url):
    return asyncio.run(transcribe_audio_async(video_url))


async def transcribe_audio_async(video_url):
    temp_video_file = f"/tmp/video_{uuid.uuid4()}.mp4"

    try:
        logging.info(f"🎧 Downloading audio from: {video_url}")

        if not video_url.lower().endswith(('.mp4', '.mov', '.webm', '.m4a')) and \
           "youtube.com" not in video_url and "youtu.be" not in video_url:
            logging.warning(f"⚠️ Skipping unsupported or invalid video URL: {video_url}")
            return None

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_video_file,
            'quiet': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        logging.info(f"✅ Download complete: {temp_video_file}")

        with open(temp_video_file, 'rb') as audio_file:
            buffer = audio_file.read()
            logging.info(f"📦 Buffer size: {len(buffer)} bytes")
            logging.info("🧠 Calling Deepgram transcription API...")

            source = {
                "buffer": buffer,
                "mimetype": "audio/mp4"
            }

            options = {
                "model": "nova-3",
                "smart_format": True
            }

            response = deepgram.listen.prerecorded.v("1").transcribe_file(source, options).to_dict()


        channels = response.get("results", {}).get("channels", [])
            if not channels:
                logging.warning("⚠️ No speech detected or transcription failed — 'channels' is empty.")
                return None

            alternatives = channels[0].get("alternatives", [])
            if not alternatives:
                logging.warning("⚠️ No transcription alternatives returned.")
                return None

            transcript = alternatives[0].get("transcript")
            if not transcript:
                logging.warning("⚠️ No actual transcript found in alternatives.")
                return None

            return transcript[:2000]

    except Exception as e:
        logging.error(f"🚨 Error during audio transcription flow: {e}")
        return None

    finally:
        if os.path.exists(temp_video_file):
            os.remove(temp_video_file)
            logging.info(f"🧹 Temporary file cleaned up: {temp_video_file}")
def transcribe_embedded_video(video_url):
    # Avoid sending web pages to yt_dlp
    if not video_url.lower().endswith((".mp4", ".webm", ".mov", ".m4a")):
        logging.warning(f"⚠️ Skipping non-video embedded URL: {video_url}")
        return None
    return transcribe_audio(video_url)


def scan_js_loaded_videos(resource_url):
    driver = None
    video_transcript = None

    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")  # Use modern headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.binary_location = "/usr/bin/google-chrome"

        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(resource_url)
        driver.implicitly_wait(5)

        # 🔍 Log all <video> elements
        video_elements = driver.find_elements(By.TAG_NAME, "video")
        logging.info(f"Found {len(video_elements)} <video> elements on the page.")
        for video in video_elements:
            video_src = video.get_attribute("src")
            logging.info(f"<video> src: {video_src}")
            if video_src:
                if "incapsula" in video_src.lower():
                    logging.warning(f"⚠️ Skipping Incapsula-protected video: {video_src}")
                    continue
                if is_valid_video_url(video_src):
                    video_transcript = asyncio.run(transcribe_audio(video_src))
                    break
                else:
                    logging.warning(f"⚠️ Skipping unsupported or invalid video URL: {video_src}")


        # 🔁 Fallback to <iframe>
        if not video_transcript:
            iframe_elements = driver.find_elements(By.TAG_NAME, "iframe")
            logging.info(f"Found {len(iframe_elements)} <iframe> elements on the page.")
            for iframe in iframe_elements:
                iframe_src = iframe.get_attribute("src")
                logging.info(f"<iframe> src: {iframe_src}")
                if iframe_src:
                    if "incapsula" in iframe_src.lower():
                        logging.warning(f"⚠️ Skipping Incapsula-protected iframe: {iframe_src}")
                        continue
                    video_transcript = transcribe_embedded_video(iframe_src)
                    break  # Stop after the first valid iframe

        return video_transcript

    except Exception as e:
        logging.error(f"Error scanning JavaScript-based videos: {e}")
        return None

    finally:
        if driver:
            driver.quit()



def fetch_resource_content(resource_url, resource_id):
    structured_transcript = []
    combined_text = ""

    try:
        response = requests.get(resource_url, timeout=10)
        response.raise_for_status()
        mime_type, _ = mimetypes.guess_type(resource_url)

        #  PDFs
        if mime_type and 'pdf' in mime_type:
            with open("temp.pdf", "wb") as f:
                f.write(response.content)

            try:
                with open("temp.pdf", "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            finally:
                os.remove("temp.pdf")

            if text:
                structured_transcript.append({
                    "type": "text",
                    "transcript": text
                })
                combined_text += text + "\n"

        #  Direct video/audio files
        elif mime_type and ('video' in mime_type or 'audio' in mime_type):
            transcript = transcribe_audio(resource_url)
            if transcript:
                structured_transcript.append({
                    "type": "video",
                    "transcript": transcript,
                    "video": resource_url
                })
                combined_text += transcript + "\n"

        else:
            #  HTML page
            soup = BeautifulSoup(response.text, "html.parser")

            # <video> tag
            video_tag = soup.find("video")
            if video_tag and video_tag.get("src"):
                transcript = transcribe_audio(video_tag.get("src"))
                if transcript:
                    structured_transcript.append({
                        "type": "video",
                        "transcript": transcript,
                        "video": video_tag.get("src")
                    })
                    combined_text += transcript + "\n"

            # <iframe> tag
            iframe_tag = soup.find("iframe")
            if iframe_tag and iframe_tag.get("src"):
                transcript = transcribe_embedded_video(iframe_tag.get("src"))
                if transcript:
                    structured_transcript.append({
                        "type": "video",
                        "transcript": transcript,
                        "video": iframe_tag.get("src")
                    })
                    combined_text += transcript + "\n"

            # Only run Selenium if no <video> or <iframe> was found
            if not video_tag and not iframe_tag:
                js_transcript = scan_js_loaded_videos(resource_url)


            # JS-loaded videos
            # Only use Selenium if nothing else worked
            if not structured_transcript:
                js_transcript = scan_js_loaded_videos(resource_url)
                if js_transcript:
                    structured_transcript.append({
                        "type": "video",
                        "transcript": js_transcript,
                        "video": "js-loaded"
                    })
                    combined_text += js_transcript + "\n"


            # Text content
            text = soup.get_text()[:2000]
            if text:
                structured_transcript.append({
                    "type": "text",
                    "transcript": text
                })
                combined_text += text + "\n"

        #  Save structured transcript to DB
        if structured_transcript:
            new_transcript = Transcript(
                resource_id=resource_id,
                transcript=structured_transcript
            )
            db.session.add(new_transcript)
            db.session.commit()
            logging.info(f"📥 Transcript saved for resource {resource_id}")

        return combined_text.strip() if combined_text else None

    except Exception as e:
        logging.error(f"Error fetching content for {resource_url}: {e}")
        return None


def clean_transcript(text):
    text = re.sub(r"\[.*?\]", "", text)  # remove timestamps or bracketed content
    text = re.sub(r"\s+", " ", text)     # normalize spacing
    text = re.sub(r"\b(uh|um|erm|hmm)\b", "", text, flags=re.IGNORECASE)  # remove filler words
    return text.strip()

def is_valid_video_url(url):
    return url and url.lower().endswith(('.mp4', '.mov', '.webm', '.m4a'))



def categorize_resource_with_ai(resource, extracted_content):
    existing_tags = [tag.name for tag in Tag.query.all()]
    resource_url = resource.url
    tags_to_add = []

    mime_type, _ = mimetypes.guess_type(resource_url)
    if mime_type:
        if 'pdf' in mime_type:
            tags_to_add.append('pdf')
        elif 'video' in mime_type:
            tags_to_add.append('video')
        elif 'html' in mime_type:
            tags_to_add.append('e-book')

    if not extracted_content:
        return list(set(tags_to_add))

    extracted_content = clean_transcript(extracted_content)


    prompt = f"""
    You are classifying educational resources. The only allowed tags are:

    {", ".join(existing_tags)}

    Assign all relevant tags to this resource from the list above — you must match the tag text exactly.

    Content:
    {extracted_content}

    Return only a JSON object in this format:
    {{"tags": ["tag1", "tag2", "tag3"]}}
    """

    try:
        response = gemini.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        ai_response_text = response.text
        json_match = re.search(r'\{.*?\}', ai_response_text, re.DOTALL)
        tags_json = json.loads(json_match.group()) if json_match else {"tags": []}
        ai_tags = tags_json.get("tags", [])

        valid_tags = []
        for tag_name in ai_tags:
            if tag_name in existing_tags:
                valid_tags.append(tag_name)
            else:
                logging.warning(f"⚠️ Ignoring unknown tag from Gemini: {tag_name}")

        tags_to_add.extend(valid_tags)
        return list(set(tags_to_add))

    except Exception as e:
        logging.error(f"Error parsing AI response: {e}")
        return tags_to_add



def assign_tags_to_resource(resource_id, tags):
    for tag_name in tags:
        tag = Tag.query.filter_by(name=tag_name).first()

        if not tag:
            logging.info(f"New tag detected: '{tag_name}' - adding to DB.")
            tag = Tag(name=tag_name)
            db.session.add(tag)
            db.session.commit()

        new_link = TagsResources(resource_id=resource_id, tag_id=tag.id)
        db.session.add(new_link)
        db.session.commit()

    logging.info(f"Tags assigned to resource {resource_id}: {tags}")


def scan_and_categorize_resources_with_ai(sample_size=5):
    logging.info(f"Starting AI tagging for {sample_size} resources...")
    resources = Resource.query.limit(sample_size).all()

    for resource in resources:
        logging.info(f"\n🔍 Processing: {resource.id} - {resource.url}")

        # NEW: fetch structured transcript and save it, return combined text for Gemini
        extracted_text = fetch_resource_content(resource.url, resource.id)

        if not extracted_text:
            logging.warning(f"No content extracted for resource {resource.id}. Skipping.")
            continue

        logging.info(f"📄 Extracted {len(extracted_text)} characters from resource {resource.id}.")

        # Classify with Gemini
        tags = categorize_resource_with_ai(resource, extracted_text)

        if tags:
            logging.info(f"🏷 Tags: {tags}")
            assign_tags_to_resource(resource.id, tags)
        else:
            logging.warning(f"No tags generated for resource {resource.id}.")

    logging.info("✅ AI tagging process complete.")

if __name__ == "__main__":
    from app import app  # make sure you import the Flask app
    with app.app_context():
        scan_and_categorize_resources_with_ai()
