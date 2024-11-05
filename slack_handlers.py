import logging
from slack_bolt.async_app import AsyncApp
from config import settings
import requests
from utils import extract_and_validate_url, get_trigger_emojis, get_emoji_message, get_emoji_configs, extract_date_from_message
from functools import wraps
import time
from datetime import datetime

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

async def get_tagged_articles_since_date(tag: str, since_date) -> list:
    """
    Query Readwise API for articles with a specific tag since a given date.
    Returns a list of articles with their titles, summaries, and dates.
    """
    articles = []
    next_page_cursor = None
    
    while True:
        try:
            url = "https://readwise.io/api/v3/list/"
            params = {
                'category': 'article',
                'tags': tag
            }
            if next_page_cursor:
                params['pageCursor'] = next_page_cursor

            response = requests.get(
                url,
                headers={"Authorization": f"Token {settings.READWISE_API_KEY}"},
                params=params
            )
            response.raise_for_status()
            data = response.json()

            # Process articles
            for article in data.get('results', []):
                created_at = datetime.fromisoformat(article.get('created_at').replace('Z', '+00:00'))
                if created_at.date() >= since_date:
                    summary = article.get('summary', 'No summary available')
                    # Truncate summary if it's too long for Slack
                    if len(summary) > 500:
                        summary = summary[:497] + "..."

                    articles.append({
                        'title': article.get('title', 'No title'),
                        'summary': summary,
                        'date': created_at.strftime('%Y-%m-%d'),
                        'url': article.get('source_url', '')
                    })
                elif created_at.date() < since_date:
                    # Since results are ordered by date, if we find an article older than since_date,
                    # we can stop paginating
                    return articles

            # Check if there are more pages
            next_page_cursor = data.get('nextPageCursor')
            if not next_page_cursor:
                break

        except requests.RequestException as e:
            logger.error(f"Error querying Readwise API: {str(e)}")
            break

    return articles

async def save_url_to_readwise(url: str, emoji: str) -> tuple[bool, str]:
    """
    Save a URL to Readwise Reader with the emoji's label as a tag.
    Returns (success, message) tuple.
    """
    try:
        # Get emoji configuration to use its label as a tag
        emoji_configs = get_emoji_configs()
        emoji_config = emoji_configs.get(emoji)
        
        # Use the emoji's label as the tag
        tag = emoji_config.label if emoji_config else "Read Later"
        
        response = requests.post(
            "https://readwise.io/api/v3/save/",
            headers={
                "Authorization": f"Token {settings.READWISE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "url": url,
                "tags": [tag],  # Only use the emoji's label as the tag
                "location": "new",  # Save to "new" items
                "saved_using": "slack-readwise-integration"  # Identify our app
            }
        )
        
        # Check response status
        if response.status_code == 201:
            data = response.json()
            reader_url = data.get('url', url)
            return True, reader_url
        elif response.status_code == 200:
            # Document already exists
            data = response.json()
            reader_url = data.get('url', url)
            return False, f"Document already exists at {reader_url}"
        else:
            response.raise_for_status()
            return False, "Unknown error occurred"
            
    except requests.RequestException as e:
        logger.error(f"Error saving URL to Readwise: {str(e)}")
        return False, str(e)

async def check_url_exists(url: str) -> bool:
    """Check if a URL already exists in Readwise Reader."""
    try:
        # Normalize the URL for comparison
        normalized_url = url.rstrip('/')
        
        # Initialize pagination
        next_cursor = None
        while True:
            params = {
                'source_url': normalized_url,  # Use source_url parameter for filtering
                'category': 'article'  # Only look for articles, not highlights
            }
            if next_cursor:
                params['pageCursor'] = next_cursor
                
            response = requests.get(
                "https://readwise.io/api/v3/list/",
                headers={
                    "Authorization": f"Token {settings.READWISE_API_KEY}"
                },
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            # Check results
            for article in data.get('results', []):
                article_url = article.get('source_url', '').rstrip('/')
                if article_url == normalized_url:
                    logger.info(f"Found exact URL match: {url}")
                    return True
            
            # Check if there are more pages
            next_cursor = data.get('nextPageCursor')
            if not next_cursor:
                break
        
        logger.info(f"No exact URL match found for: {url}")
        return False
        
    except requests.RequestException as e:
        logger.error(f"Error checking URL in Readwise: {str(e)}")
        return False

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
            
            # Check if the message contains a date
            date_from_message = extract_date_from_message(message)
            if date_from_message:
                # Get emoji configuration to use its label as a tag
                emoji_configs = get_emoji_configs()
                emoji_config = emoji_configs.get(reaction)
                tag = emoji_config.label if emoji_config else "Read Later"
                
                # Query articles with the tag since the given date
                articles = await get_tagged_articles_since_date(tag, date_from_message)
                
                if articles:
                    # Format the response message
                    response_text = f"Here are the articles tagged with '{tag}' since {date_from_message}:\n\n"
                    for article in articles:
                        response_text += f"*{article['title']}*\n"
                        response_text += f"Added on: {article['date']}\n"
                        response_text += f"Summary: {article['summary']}\n"
                        if article['url']:
                            response_text += f"URL: {article['url']}\n"
                        response_text += "\n"
                    
                    # Split message if it's too long for Slack
                    if len(response_text) > 3000:
                        chunks = [response_text[i:i+3000] for i in range(0, len(response_text), 3000)]
                        for chunk in chunks:
                            await client.chat_postMessage(
                                channel=channel_id,
                                text=chunk,
                                thread_ts=message_ts
                            )
                    else:
                        await client.chat_postMessage(
                            channel=channel_id,
                            text=response_text,
                            thread_ts=message_ts
                        )
                else:
                    await client.chat_postMessage(
                        channel=channel_id,
                        text=f"No articles found with tag '{tag}' since {date_from_message}",
                        thread_ts=message_ts
                    )
                return
            
            # If no date in message, proceed with normal URL saving behavior
            url = extract_and_validate_url(message)
            if url:
                # First, check if the URL already exists
                url_exists = await check_url_exists(url)
                if url_exists:
                    logger.info(f"URL already exists in Readwise, skipping: {url}")
                    # No message is posted to Slack for duplicate URLs
                else:
                    # If the URL doesn't exist, save it with the emoji's tag
                    success, result = await save_url_to_readwise(url, reaction)
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
                        logger.error(f"Failed to save URL to Readwise: {result}")
        else:
            logger.warning("No message found in the conversation history")
    except Exception as e:
        logger.error(f"Error handling reaction: {str(e)}")
