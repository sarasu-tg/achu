import os
import asyncio
import time
import requests  # For downloading the image from the URL
from pyrogram import Client, filters
from helper.utils import progress_for_pyrogram
from helper.database import jishubotz
from config import Config

BASE_DOWNLOAD_PATH = "downloads"
file_queue = asyncio.Queue()

# Your channel ID (replace with your actual channel ID)
CHANNEL_ID = "-1001957130711"

def create_user_download_path(user_id):
    path = os.path.join(BASE_DOWNLOAD_PATH, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path

async def download_thumbnail(image_url, save_path):
    """Download image from a URL and save it locally."""
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
            return save_path
        else:
            print(f"[ERROR] Failed to download thumbnail: {response.status_code}")
            return None
    except Exception as e:
        print(f"[ERROR] Error downloading thumbnail: {e}")
        return None

async def process_file(client, message):
    """Process a single file."""
    user_id = message.from_user.id
    user_download_path = create_user_download_path(user_id)
    original_file_name = message.document.file_name if message.document else "uploaded_file"
    file_extension = os.path.splitext(original_file_name)[1] or ".bin"
    file_path = os.path.join(user_download_path, f"processed_file{file_extension}")
    
    # Fetch caption and process it
    caption = await jishubotz.get_caption(user_id) or "**Here is your file!**"
    caption = caption.replace("{filename}", original_file_name)
    file_size = message.document.file_size
    caption = caption.replace("{filesize}", f"{file_size / (1024 * 1024):.2f} MB")
    caption = caption.replace("{fileduration}", "Duration not available")

    # Direct thumbnail URL
    image_url = Config.GLOBAL_THUMBNAIL_URL  # Replace with your image URL
    thumbnail_path = os.path.join(user_download_path, "thumbnail.jpg")
    thumb_path = await download_thumbnail(image_url, thumbnail_path)
    
    # Download the file
    status_message = await message.reply("`Download in progress...`")
    try:
        await client.download_media(
            message=message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("`Download in progress...`", status_message, time.time())
        )
    except Exception as e:
        await status_message.edit(f"Error during download: {e}")
        return

    # Upload to both user and channel
    await status_message.edit("`Uploading file...`")
    try:
        # Send file to user and channel
        await asyncio.gather(
            client.send_document(
                message.chat.id,
                document=file_path,
                caption=caption,
                file_name=original_file_name,
                thumb=thumb_path if thumb_path else None,  # Use the downloaded thumbnail
                progress=progress_for_pyrogram,
                progress_args=("`Upload in progress...`", status_message, time.time())
            ),
            client.send_document(
                chat_id=CHANNEL_ID,
                document=file_path,
                caption=caption,
                file_name=original_file_name,
                thumb=thumb_path if thumb_path else None,  # Use the downloaded thumbnail
            )
        )
    except Exception as e:
        await status_message.edit(f"Error during upload: {e}")
        return
    finally:
        # Cleanup files
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        await status_message.delete()

    print(f"[DEBUG] File processing completed for user {user_id}")

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def enqueue_file(client, message):
    """Add file to the queue."""
    print(f"[DEBUG] File added to queue by user: {message.from_user.id}")
    await file_queue.put(message)
    
async def worker(client):
    """Worker function to process files sequentially."""
    print("[DEBUG] Worker started.")
    while True:
        print("[DEBUG] Waiting for a file in the queue...")
        message = await file_queue.get()
        try:
            print(f"[DEBUG] File dequeued for processing: {message.chat.id}")
            await process_file(client, message)
        except Exception as e:
            print(f"[DEBUG] Error in worker: {e}")
        finally:
            file_queue.task_done()
            print("[DEBUG] Worker finished processing a file.")

def start_worker(client):
    """Initialize the worker task."""
    asyncio.create_task(worker(client))
    print("[DEBUG] Worker loop initialized.")
    
