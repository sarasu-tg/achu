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
CHANNEL_ID = "-1002130121487"

def create_user_download_path(user_id):
    path = os.path.join(BASE_DOWNLOAD_PATH, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path

async def process_file(client, message):
    """Process a single file."""
    print(f"[DEBUG] Starting file processing for user: {message.from_user.id}")
    user_id = message.from_user.id
    user_download_path = create_user_download_path(user_id)
    
    # Extract the original file name and extension
    original_file_name = message.document.file_name if message.document else "uploaded_file"
    file_extension = os.path.splitext(original_file_name)[1]
    if not file_extension:
        file_extension = ".bin"  # Default fallback extension
    
    file_path = os.path.join(user_download_path, f"processed_file{file_extension}")

    # Fetch the user's caption from the database
    caption = await jishubotz.get_caption(user_id)
    if not caption:
        caption = "**Here is your file!**"  # Default caption if none is set

    # Replace {filename}, {filesize}, and {fileduration} in the caption
    caption = caption.replace("{filename}", original_file_name)
    file_size = message.document.file_size
    caption = caption.replace("{filesize}", f"{file_size / (1024 * 1024):.2f} MB")

    # For videos and audios, add the duration
    file_duration = ""
    if message.video or message.audio:
        # Assuming you have a function to get file duration (via ffmpeg or any method)
        file_duration = "Duration not available"  # Replace with actual duration fetching logic
        caption = caption.replace("{fileduration}", file_duration)

    # Check if user has set a custom thumbnail
    ph_path = None
    c_thumb = await jishubotz.get_thumbnail(user_id)
    if c_thumb:
        try:
            ph_path = await client.download_media(c_thumb)
            _, _, ph_path = await fix_thumb(ph_path)  # Assuming this fixes the thumbnail if needed
        except Exception as e:
            print(f"[DEBUG] Error processing thumbnail: {e}")
            return await message.reply(f"Error processing thumbnail: {e}")

    # Download the file
    status_message = await message.reply("`Downloading file...`")
    try:
        await client.download_media(
            message=message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("`Download in progress...`", status_message, time.time())
        )
    except Exception as e:
        print(f"[DEBUG] Error during download: {e}")
        await status_message.edit(f"Error during download: {e}")
        return

    # Upload the file with the custom caption and thumbnail to the user
    await status_message.edit("`Uploading file...`")
    try:
        # Send to the user first
        await client.send_document(
            message.chat.id,
            document=file_path,
            caption=caption,  # Use the custom caption
            file_name=original_file_name,  # Preserve the original file name
            thumb=ph_path,  # Attach the thumbnail (if any)
            progress=progress_for_pyrogram,
            progress_args=("`Upload in progress...`", status_message, time.time())
        )
        
        # Forward the file to the channel (no announcement)
        await client.send_document(
            -1001957130711,
            document=file_path,
            caption=caption,  # Use the custom caption for the channel too
            file_name=original_file_name,  # Preserve the original file name
            thumb=ph_path,  # Attach the thumbnail (if any)
        )

    except Exception as e:
        print(f"[DEBUG] Error during upload: {e}")
        await status_message.edit(f"Error during upload: {e}")
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
        if ph_path and os.path.exists(ph_path):
            os.remove(ph_path)
        await status_message.delete()
    print(f"[DEBUG] File processing complete for user: {user_id}")

    
@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def enqueue_file(client, message):
    """Add file to the queue."""
    print(f"[DEBUG] File added to queue by user: {message.from_user.id}")
    await file_queue.put(message)
    await message.reply("`File added to the queue. Processing...`")

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
            
