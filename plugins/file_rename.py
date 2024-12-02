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
    caption = await jishubotz.get_caption(user_id) or "**Here is your file!**"
    caption = caption.replace("{filename}", original_file_name)
    file_size = message.document.file_size
    caption = caption.replace("{filesize}", f"{file_size / (1024 * 1024):.2f} MB")
    caption = caption.replace("{fileduration}", "Duration not available")

    # Check for custom thumbnail
    ph_path = None
    c_thumb = await jishubotz.get_thumbnail(user_id)
    if c_thumb:
        try:
            print("[DEBUG] Downloading and processing thumbnail...")
            ph_path = await client.download_media(c_thumb)
            _, _, ph_path = await fix_thumb(ph_path)
            print(f"[DEBUG] Thumbnail processed: {ph_path}")
        except Exception as e:
            print(f"[DEBUG] Error processing thumbnail: {e}")
            await message.reply(f"Error processing thumbnail: {e}")
            return
    else:
        print("[DEBUG] No custom thumbnail set by the user.")

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
                thumb=ph_path if ph_path else None,  # Ensure thumbnail consistency
                progress=progress_for_pyrogram,
                progress_args=("`Upload in progress...`", status_message, time.time())
            ),
            client.send_document(
                chat_id=CHANNEL_ID,
                document=file_path,
                caption=caption,
                file_name=original_file_name,
                thumb=ph_path if ph_path else None,  # Ensure thumbnail consistency
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

    print(f"[DEBUG] File processing completed for user {user_id}")
