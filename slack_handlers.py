import logging
from slack_bolt.async_app import AsyncApp
from config import settings
import requests
from utils import extract_and_validate_url, get_trigger_emojis, get_emoji_message, get_emoji_configs
from functools import wraps
import time
from datetime import datetime, date, timedelta
import dateparser
import urllib.parse

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class EventDeduplicator:
    def __init__(self):
        self.processed_events = {}

    def deduplicate(self, ttl=60):
        def decorator(func):
            @wraps(func)
            async def wrapper(event, say, client):
                event_key = f"{event['event_ts']}:{event['item']['channel']}:{event['item']['ts']}"
                current_time = time.time()

                if event_key in self.processed_events:
                    if current_time - self.processed_events[event_key] < ttl:
                        logger.info(f"Duplicate event detected, skipping: {event_key}")
                        return

                self.processed_events[event_key] = current_time
                self.processed_events = {k: v for k, v in self.processed_events.items() if current_time - v < ttl}

                return await func(event, say, client)
            return wrapper
        return decorator

app = AsyncApp(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET
)
trigger_emojis = get_trigger_emojis()
deduplicator = EventDeduplicator()

class WallabagClient:
    def __init__(self):
        self.access_token = None
        self.token_expires = 0
        # Ensure the base URL doesn't end with a slash
        self.base_url = settings.WALLABAG_URL.rstrip('/')

    async def get_token(self):
        """Get or refresh the Wallabag access token."""
        current_time = time.time()
        if self.access_token and current_time < self.token_expires:
            return self.access_token

        try:
            # Ensure all credentials are properly URL encoded
            data = {
                "grant_type": "password",
                "client_id": urllib.parse.quote(settings.WALLABAG_CLIENT_ID),
                "client_secret": urllib.parse.quote(settings.WALLABAG_CLIENT_SECRET),
                "username": urllib.parse.quote(settings.WALLABAG_USERNAME),
                "password": urllib.parse.quote(settings.WALLABAG_PASSWORD)
            }

            # Log the request URL and data (without sensitive info) for debugging
            logger.info(f"Requesting token from: {self.base_url}/oauth/v2/token")
            logger.info(f"Using client_id: {settings.WALLABAG_CLIENT_ID}")

            response = requests.post(
                f"{self.base_url}/oauth/v2/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data=data,
                timeout=10
            )

            # Log the response status and content for debugging
            logger.info(f"Token request status code: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"Token request failed with content: {response.text}")

            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            self.token_expires = current_time + data["expires_in"] - 300  # Refresh 5 minutes before expiry
            return self.access_token
        except Exception as e:
            logger.error(f"Error getting Wallabag token: {str(e)}")
            if isinstance(e, requests.exceptions.RequestException):
                logger.error(f"Response content: {e.response.text if hasattr(e, 'response') else 'No response content'}")
            raise

    async def get_headers(self):
        """Get headers with current access token."""
        token = await self.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    async def save_url(self, url: str, tags: list[str]) -> tuple[bool, str]:
        """Save a URL to Wallabag with tags."""
        try:
            headers = await self.get_headers()
            response = requests.post(
                f"{self.base_url}/api/entries",
                headers=headers,
                json={
                    "url": url,
                    "tags": tags
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return True, data.get('url', url)
        except requests.RequestException as e:
            logger.error(f"Error saving URL to Wallabag: {str(e)}")
            return False, str(e)

    async def check_url_exists(self, url: str) -> bool:
        """Check if a URL already exists in Wallabag."""
        try:
            headers = await self.get_headers()
            response = requests.get(
                f"{self.base_url}/api/entries/exists",
                headers=headers,
                params={"url": url},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('exists', False)
        except requests.RequestException as e:
            logger.error(f"Error checking URL in Wallabag: {str(e)}")
            return False

    async def get_tagged_articles(self, tag: str, since_date: date) -> list:
        """Get articles with specific tag since a given date."""
        try:
            headers = await self.get_headers()
            articles = []
            page = 1
            
            # Convert the date to a timestamp at midnight of that day
            since_timestamp = int(datetime.combine(since_date, datetime.min.time()).timestamp())
            logger.info(f"Fetching articles with tag '{tag}' since timestamp: {since_timestamp}")
            
            while True:
                response = requests.get(
                    f"{self.base_url}/api/entries",
                    headers=headers,
                    params={
                        "tags": tag,  # Remove the list brackets as Wallabag expects a string
                        "since": since_timestamp,
                        "page": page,
                        "perPage": 100
                    },
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                
                if not data.get('_embedded', {}).get('items'):
                    break
                    
                for entry in data['_embedded']['items']:
                    articles.append({
                        'title': entry.get('title', 'No title'),
                        'date': datetime.fromtimestamp(entry['created_at']).strftime('%Y-%m-%d'),
                        'url': entry.get('url', '')
                    })
                
                if page >= data.get('pages', 1):
                    break
                    
                page += 1
                
            return articles
        except Exception as e:
            logger.error(f"Error getting tagged articles from Wallabag: {str(e)}")
            raise  # Re-raise the exception to handle it in the calling function

# Initialize Wallabag client
wallabag_client = WallabagClient()

async def get_tagged_articles_since_date(tag: str, since_date: date) -> list:
    """Get articles with a specific tag since a given date."""
    return await wallabag_client.get_tagged_articles(tag, since_date)

async def save_url_to_wallabag(url: str, emoji: str) -> tuple[bool, str]:
    """Save a URL to Wallabag with the emoji's label as a tag."""
    try:
        # Get emoji configuration to use its label as a tag
        emoji_configs = get_emoji_configs()
        emoji_config = emoji_configs.get(emoji)
        
        # Use the emoji's label as the tag
        tag = emoji_config.label if emoji_config else "Read Later"
        
        return await wallabag_client.save_url(url, [tag])
            
    except Exception as e:
        logger.error(f"Error saving URL to Wallabag: {str(e)}")
        return False, str(e)

async def check_url_exists(url: str) -> bool:
    """Check if a URL already exists in Wallabag."""
    return await wallabag_client.check_url_exists(url)

@app.command("/retrieve-articles")
async def handle_retrieve_command(ack, respond, command):
    """Handle the /retrieve-articles slash command."""
    await ack()
    
    try:
        # Parse command text (expected format: "emoji date")
        parts = command['text'].strip().split(maxsplit=1)
        if len(parts) != 2:
            await respond({
                "response_type": "ephemeral",
                "text": "Please provide both an emoji and a date. Example: `/retrieve-articles :bookmark: 2024-01-01`"
            })
            return

        emoji, date_str = parts
        
        # Remove colons from emoji if present
        emoji = emoji.strip(':')
        
        # Validate emoji
        emoji_configs = get_emoji_configs()
        if emoji not in emoji_configs:
            await respond({
                "response_type": "ephemeral",
                "text": f"Invalid emoji. Valid options are: {', '.join([f':{e}:' for e in emoji_configs.keys()])}"
            })
            return
        
        # Parse date
        parsed_date = dateparser.parse(date_str)
        if not parsed_date:
            await respond({
                "response_type": "ephemeral",
                "text": "Could not parse the date. Please provide a clear date format like '2024-01-01' or 'January 1st'"
            })
            return

        # Convert to date object
        since_date = parsed_date.date()

        # Validate date is not in the future
        if since_date > date.today():
            await respond({
                "response_type": "ephemeral",
                "text": "The date cannot be in the future."
            })
            return

        # Validate date is not too far in the past (e.g., more than 1 year)
        if since_date < date.today() - timedelta(days=365):
            await respond({
                "response_type": "ephemeral",
                "text": "Please select a date within the last year."
            })
            return

        # Get tag from emoji config
        tag = emoji_configs[emoji].label
        
        # Show initial response
        await respond({
            "response_type": "in_channel",
            "text": f"Retrieving articles tagged with '{tag}' since {since_date}..."
        })
        
        # Query articles
        articles = await get_tagged_articles_since_date(tag, since_date)
        
        if not articles:
            await respond({
                "response_type": "in_channel",
                "text": f"No articles found with tag '{tag}' since {since_date}"
            })
            return
        
        # Format response as markdown
        response_text = f"*Articles tagged with '{tag}' since {since_date}*\n\n"
        
        for article in articles:
            response_text += (
                f"• *{article['title']}*\n"
                f"  Added on: {article['date']}\n"
                f"  <{article['url']}|Read article>\n\n"
            )

        # Split message if it's too long for Slack (max 40000 chars)
        max_length = 40000
        chunks = [response_text[i:i + max_length] for i in range(0, len(response_text), max_length)]
        
        for chunk in chunks:
            await respond({
                "response_type": "in_channel",
                "text": chunk
            })
            
    except Exception as e:
        logger.error(f"Error handling retrieve command: {str(e)}")
        await respond({
            "response_type": "ephemeral",
            "text": f"An error occurred: {str(e)}"
        })

@app.event("reaction_added")
@deduplicator.deduplicate(ttl=60)  # Set TTL to 60 seconds
async def handle_reaction(event, say, client):
    reaction = event['reaction']
    if reaction not in trigger_emojis:
        return

    channel_id = event["item"]["channel"]
    message_ts = event["item"]["ts"]
    try:
        result = await client.conversations_history(
            channel=channel_id,
            latest=message_ts,
            limit=1,
            inclusive=True
        )
        if result.data.get("messages"):
            message = result.data["messages"][0]
            url = extract_and_validate_url(message)
            if url:
                # First, check if the URL already exists
                url_exists = await check_url_exists(url)
                if url_exists:
                    logger.info(f"URL already exists in Wallabag, skipping: {url}")
                    # No message is posted to Slack for duplicate URLs
                else:
                    # If the URL doesn't exist, save it with the emoji's tag
                    success, result = await save_url_to_wallabag(url, reaction)
                    if success:
                        # Get custom message for the specific emoji
                        custom_message = get_emoji_message(reaction)
                        reply_text = f"{custom_message}: {result}"
                        await client.chat_postMessage(
                            channel=channel_id,
                            text=reply_text,
                            thread_ts=message_ts
                        )
                    else:
                        logger.error(f"Failed to save URL to Wallabag: {result}")
        else:
            logger.warning("No message found in the conversation history")
    except Exception as e:
        logger.error(f"Error handling reaction: {str(e)}")
