import os
import sys
import re
import asyncio
import edge_tts
import boto3
from bs4 import BeautifulSoup
import markdown
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
VOICE = "en-IN-PrabhatNeural"  

# Cloudflare R2 Settings 
# Get these from your Cloudflare Dashboard -> R2 -> Manage R2 API Tokens
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "YOUR_ACCOUNT_ID")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "YOUR_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "YOUR_SECRET_KEY")
R2_BUCKET = os.environ.get("R2_BUCKET", "YOUR_BUCKET_NAME")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "https://pub-xxxxxx.r2.dev")
# ---------------------

def extract_text(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Strip TOML front matter (+++)
    text = re.sub(r"^\+\+\+[\s\S]*?\+\+\+\s*", "", content)
    
    # Strip YAML front matter (---) just in case
    text = re.sub(r"^---[\s\S]*?---\s*", "", text)
    
    # Strip markdown codeblocks
    text = re.sub(r"```[\s\S]*?```", "", text)

    # Strip footnote markers and definitions
    text = re.sub(r"(<!--\s*Footnote\s*-->|\[\^\d+\]:[\s\S]*$)", "", text)
    text = re.sub(r"\^\[.*?\]", "", text)
    text = re.sub(r"\[\^.*?\]", "", text)
    
    # Convert remaining markdown to HTML and strip tags
    html = markdown.markdown(text)
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ").strip()

async def generate_audio(text, output_file):
    print(f"Generating 48 kbps MP3 with {VOICE}...")
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(output_file)

def upload_to_r2(local_file, remote_file):
    print(f"Uploading to R2 bucket '{R2_BUCKET}'...")
    s3 = boto3.client('s3',
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto"
    )
    s3.upload_file(
        local_file, 
        R2_BUCKET, 
        remote_file,
        ExtraArgs={"ContentType": "audio/mpeg"}
    )
    return f"{R2_PUBLIC_URL}/{remote_file}"

async def main():
    if len(sys.argv) < 2:
        print("Usage: python tts_pipeline.py path/to/post.md")
        sys.exit(1)
        
    md_path = sys.argv[1]
    slug = os.path.splitext(os.path.basename(md_path))[0]
    mp3_filename = f"{slug}.mp3"
    
    text = extract_text(md_path)
    if not text:
        print("No readable text found in markdown.")
        return

    # 1. Generate MP3
    await generate_audio(text, mp3_filename)
    
    # 2. Upload to Cloudflare R2
    public_url = upload_to_r2(mp3_filename, mp3_filename)
    
    # 3. Output YAML snippet
    print("\n=== SUCCESS ===")
    print(f"Add this to the front matter of {md_path}:")
    print(f"audio: \"{public_url}\"")
    
    # Cleanup temporary local MP3
    os.remove(mp3_filename)

if __name__ == "__main__":
    asyncio.run(main())
