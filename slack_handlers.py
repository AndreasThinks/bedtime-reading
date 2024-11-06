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
        self.base_url = settings.WALLABAG_URL.rstrip('/')

    async def get_token(self):
        """Get or refresh the Wallabag access token."""
        current_time = time.time()
        if self.access_token and current_time < self.token_expires:
            return self.access_token

        try:
            data = {
                "grant_type": "password",
                "client_id": urllib.parse.quote(settings.WALLABAG_CLIENT_ID),
                "client_secret": urllib.parse.quote(settings.WALLABAG_CLIENT_SECRET),
                "username": urllib.parse.quote(settings.WALLABAG_USERNAME),
                "password": urllib.parse.quote(settings.WALLABAG_PASSWORD)
            }

            response = requests.post(
                f"{self.base_url}/oauth/v2/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=data,
                timeout=10
            )

            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            self.token_expires = current_time + data["expires_in"] - 300
            return self.access_token
        except Exception as e:
            logger.error(f"Error getting Wallabag token: {str(e)}")
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
                json={"url": url, "tags": tags},
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
            
            if not isinstance(since_date, date):
                raise ValueError(f"since_date must be a date object, got {type(since_date)}")
            
            dt = datetime.combine(since_date, datetime.min.time())
            since_timestamp = int(dt.timestamp())
            
            while True:
                try:
                    response = requests.get(
                        f"{self.base_url}/api/entries",
                        headers=headers,
                        params={
                            "tags": tag,
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
                        try:
                            created_at = dateparser.parse(entry['created_at'])
                            if not created_at:
                                continue
                                
                            article = {
                                'title': entry.get('title', 'No title'),
                                'date': created_at.strftime('%Y-%m-%d'),
                                'url': entry.get('url', '')
                            }
                            articles.append(article)
                        except (ValueError, TypeError) as e:
                            logger.error(f"Error processing entry: {str(e)}")
                            continue
                    
                    if page >= data.get('pages', 1):
                        break
                        
                    page += 1
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error on page {page}: {str(e)}")
                    raise
                
            return articles
            
        except Exception as e:
            logger.error(f"Error getting tagged articles from Wallabag: {str(e)}")
            raise

# Initialize Wallabag client
wallabag_client = WallabagClient()

async def get_tagged_articles_since_date(tag: str, since_date: date) -> list:
    """Get articles with a specific tag since a given date."""
    try:
        return await wallabag_client.get_tagged_articles(tag, since_date)
    except Exception as e:
        logger.error(f"Error in get_tagged_articles_since_date: {str(e)}")
        raise

async def save_url_to_wallabag(url: str, emoji: str) -> tuple[bool, str]:
    """Save a URL to Wallabag with the emoji's label as a tag."""
    try:
        emoji_configs = get_emoji_configs()
        emoji_config = emoji_configs.get(emoji)
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
        parts = command['text'].strip().split(maxsplit=1)
        if len(parts) != 2:
            await respond({
                "response_type": "ephemeral",
                "text": "Please provide both an emoji and a date. Example: `/retrieve-articles :bookmark: 2024-01-01`"
            })
            return

        emoji, date_str = parts
        emoji = emoji.strip(':')
        
        emoji_configs = get_emoji_configs()
        if emoji not in emoji_configs:
            await respond({
                "response_type": "ephemeral",
                "text": f"Invalid emoji. Valid options are: {', '.join([f':{e}:' for e in emoji_configs.keys()])}"
            })
            return
        
        parsed_date = dateparser.parse(date_str)
        if not parsed_date:
            await respond({
                "response_type": "ephemeral",
                "text": "Could not parse the date. Please provide a clear date format like '2024-01-01' or 'January 1st'"
            })
            return

        since_date = parsed_date.date()

        if since_date > date.today():
            await respond({
                "response_type": "ephemeral",
                "text": "The date cannot be in the future."
            })
            return

        if since_date < date.today() - timedelta(days=365):
            await respond({
                "response_type": "ephemeral",
                "text": "Please select a date within the last year."
            })
            return

        tag = emoji_configs[emoji].label
        
        await respond({
            "response_type": "in_channel",
            "text": f"Retrieving articles tagged with '{tag}' since {since_date}..."
        })
        
        try:
            articles = await get_tagged_articles_since_date(tag, since_date)
            
            if not articles:
                await respond({
                    "response_type": "in_channel",
                    "text": f"No articles found with tag '{tag}' since {since_date}"
                })
                return
            
            response_text = f"*Articles tagged with '{tag}' since {since_date}*\n\n"
            
            for article in articles:
                response_text += (
                    f"• *{article['title']}*\n"
                    f"  Added on: {article['date']}\n"
                    f"  <{article['url']}|Read article>\n\n"
                )

            max_length = 40000
            chunks = [response_text[i:i + max_length] for i in range(0, len(response_text), max_length)]
            
            for chunk in chunks:
                await respond({
                    "response_type": "in_channel",
                    "text": chunk
                })
                
        except Exception as e:
            logger.error(f"Error retrieving articles: {str(e)}")
            await respond({
                "response_type": "ephemeral",
                "text": f"Error retrieving articles: {str(e)}"
            })
            
    except Exception as e:
        logger.error(f"Error handling retrieve command: {str(e)}")
        await respond({
            "response_type": "ephemeral",
            "text": f"An error occurred: {str(e)}"
        })

@app.event("reaction_added")
@deduplicator.deduplicate(ttl=60)
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
                url_exists = await check_url_exists(url)
                if url_exists:
                    logger.info(f"URL already exists in Wallabag, skipping: {url}")
                else:
                    success, result = await save_url_to_wallabag(url, reaction)
                    if success:
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
