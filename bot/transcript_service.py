from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound


def get_transcript(video_id: str):
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        # Try to find a transcript in priority order
        try:
            # Hindi, English, Spanish, German, French, Malayalam, Tamil, Telugu
            transcript = transcript_list.find_transcript(['hi', 'en', 'es', 'de', 'fr', 'ml', 'ta', 'te'])
        except NoTranscriptFound:
            # Fallback to the first available transcript if priority list fails
            transcript = next(iter(transcript_list))

        data = transcript.fetch()
        full_text = " ".join([entry.text for entry in data])

        return True, full_text

    except TranscriptsDisabled:
        return False, "Transcripts are disabled for this video."

    except NoTranscriptFound:
        return False, "No transcript found for this video."

    except Exception as e:
        return False, f"Unexpected error: {str(e)}"