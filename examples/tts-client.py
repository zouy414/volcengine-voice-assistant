#!/usr/bin/env python3
import argparse
import asyncio
import logging
import uuid

from custom_components.volcengine_voice_assistant.sdk.tts import Client


async def run(text: str, voice_type: str, file: str, url: str, app_key: str, access_key: str,  resource_id: str):
    logger: logging.Logger = logging.getLogger(__name__)
    async with Client(url, app_key, access_key, resource_id) as client:
        resp = await client.async_connect()
        logger.info("Connect successfully, response: %s", resp)

        try:
            resp = await client.async_start_session(str(uuid.uuid4()), voice_type)
            logger.info("Start session successfully, response: %s", resp)

            async def sender():
                try:
                    await client.async_send_task(text)
                except Exception as e:
                    logger.exception(f"sender text failed: {e}")
                    raise
                finally:
                    await client.async_finish_session()

            # Start sending characters in background
            sender_task = asyncio.create_task(sender())

            try:
                audio_data = bytearray()
                async for resp in client.async_recv():
                    audio_data.extend(resp.payload)

                await sender_task

                with open(file, "wb") as f:
                    f.write(audio_data)
            except Exception as e:
                logger.exception(f"Failed to recv audio: {e}")

                try:
                    sender_task.cancel()
                    await sender_task
                    logger.info("Sender task cancelled successfully")
                except asyncio.CancelledError:
                    pass

                raise
        except Exception as e:
            logger.exception(f"TSS failed: {e}")
        finally:
            await client.async_disconnect()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--app-key", required=True, help="APP Key")
    parser.add_argument("--access-key", required=True, help="Access Key")
    parser.add_argument("--text", required=True, help="Text to convert")
    parser.add_argument("--file", type=str, required=True,
                        help="Audio file output path")

    parser.add_argument(
        "--resource-id", default="seed-tts-2.0", help="Resource ID")
    parser.add_argument(
        "--voice-type", default="zh_female_vv_uranus_bigtts", help="Voice type")
    parser.add_argument("--encoding", default="mp3",
                        help="Output file encoding")
    parser.add_argument(
        "--url", default="wss://openspeech.bytedance.com/api/v3/tts/bidirection", help="WebSocket endpoint URL")

    args = parser.parse_args()
    asyncio.run(
        run(
            args.text,
            args.voice_type,
            args.file,
            args.url,
            args.app_key,
            args.access_key,
            args.resource_id
        )
    )
