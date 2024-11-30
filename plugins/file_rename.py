import os
import asyncio
import time
from pyrogram import Client, filters
from helper.ffmpeg import fix_thumb  # Ensure you have this helper function to fix thumbnails
from helper.utils import progress_for_pyrogram
from helper.database import jishubotz

BASE_DOWNLOAD_PATH = "downloads"
file_queue = asyncio.Queue()

# Your channel ID (replace with your actual channel ID)
CHANNEL_ID = "-1001957130711"

def create_user_download_path(user_id):
    path = os.path.join(BASE_DOWNLOAD_PATH, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path
            
async def process_file(client, message):
    """Process a single file."""
    user_id = message.from_user.id
    user_download_path = create_user_download_path(user_id)
    original_file_name = message.document.file_name if message.document else "uploaded_file"
    file_extension = os.path.splitext(original_file_name)[1] or ".bin"
    file_path = os.path.join(user_download_path, f"processed_file{file_extension}")
    
    # Fetch caption and process it
    caption = await jishubotz.get_caption(user_id) or "Here is your file!"
    caption = caption.replace("{filename}", original_file_name)
    file_size = message.document.file_size
    caption = caption.replace("{filesize}", f"{file_size / (1024 * 1024):.2f} MB")
    caption = caption.replace("{fileduration}", "Duration not available")

    # Check for custom thumbnail
    ph_path = None
    c_thumb = await jishubotz.get_thumbnail(user_id)
    if c_thumb:
        try:
            ph_path = await client.download_media(c_thumb)
            _, _, ph_path = await fix_thumb(ph_path)
        except Exception as e:
            print(f"[DEBUG] Error processing thumbnail: {e}")
            return await message.reply(f"Error processing thumbnail: {e}")

    # Download the file
    status_message = await message.reply("Download in progress...")
    try:
        await client.download_media(
            message=message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("Download in progress...", status_message, time.time())
        )
    except Exception as e:
        await status_message.edit(f"Error during download: {e}")
        return

    # Upload to both user and channel
    await status_message.edit("Uploading file...")
    try:
        await asyncio.gather(
            client.send_document(
                message.chat.id,
                document=file_path,
                caption=caption,
                file_name=original_file_name,
                thumb=ph_path,
                progress=progress_for_pyrogram,
                progress_args=("Upload in progress...", status_message, time.time())
            ),
            client.send_document(
                chat_id=CHANNEL_ID,
                document=file_path,
                caption=caption,
                file_name=original_file_name,
                thumb=ph_path,
            )
        )
    except Exception as e:
        await status_message.edit(f"Error during upload: {e}")
        return
    finally:
        # Cleanup files
        if os.path.exists(file_path):
            os.remove(file_path)
        if ph_path and os.path.exists(ph_path):
            os.remove(ph_path)
        await status_message.delete()
            

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
