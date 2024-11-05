# Slack Readwise Integration

This application integrates Slack with Readwise Reader, allowing you to save URLs shared in Slack to your Readwise account with customizable reactions and messages.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/AzS2fY?referralCode=mOVLfw)

## Features
- Save URLs shared in Slack to Readwise Reader when specific emoji reactions are added
- Each emoji reaction saves the article with its specific tag (one tag per article)
- Query articles by tag and date using emoji reactions
- Custom confirmation messages for each emoji reaction
- Configurable newsletter tags for including articles in the newsletter
- Automatic duplicate detection to prevent saving the same article twice
- Configurable rate limiting
- Secure handling of environment variables

## Deployment
Click the "Deploy to Railway" button above to start the deployment process. Don't worry if you don't have all of these yet, you'll get the rest after deploying your Slack App.

Required Environment Variables:
- `SLACK_BOT_TOKEN`: Your Slack Bot Token
- `SLACK_SIGNING_SECRET`: Your Slack Signing Secret
- `READWISE_API_KEY`: Your Readwise API Key
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts (e.g., your-app-name.railway.app)

Optional Environment Variables:
- `RATE_LIMIT_PER_MINUTE`: Number of requests allowed per minute (default: 20)
- `EMOJI_CONFIGS`: Configuration for emoji reactions in the format "emoji1:label1:message1;emoji2:label2:message2"
- `NEWSLETTER_TAGS`: Comma-separated list of tags to include in the newsletter (default: "Newsletter")

Example Configuration:

1. Emoji Configuration:
```
EMOJI_CONFIGS=bookmark:Read Later:📚 Added to your reading list;brain:Study Material:🧠 Saved as study material;star:Must Read:⭐ Marked as must-read
```

This creates three different reactions with distinct purposes:
- :bookmark: - Tags articles as "Read Later" for general reading
- :brain: - Tags articles as "Study Material" for learning resources
- :star: - Tags articles as "Must Read" for important content

2. Newsletter Tags:
```
NEWSLETTER_TAGS=Must Read,Study Material
```

This configuration would include articles tagged with either "Must Read" or "Study Material" in the newsletter. You can specify any combination of tags that match your emoji configurations.

Each article is saved with exactly one tag based on the emoji used. For example:
- Using :bookmark: saves the article with only the "Read Later" tag
- Using :brain: saves the article with only the "Study Material" tag
- Using :star: saves the article with only the "Must Read" tag

Articles with tags listed in NEWSLETTER_TAGS will be included in the newsletter. If NEWSLETTER_TAGS is not set, it defaults to including only articles tagged with "Newsletter".

If EMOJI_CONFIGS is not set, it defaults to using the :bookmark: emoji with a standard message and "Read Later" tag.

## Usage
The application supports two main modes of operation:

### 1. Saving URLs to Readwise
1. Add the Slack bot to your workspace and invite it to the desired channels.
2. When a message containing a URL is posted, react to it with one of your configured emojis.
3. The bot will:
   - Extract the URL from the message
   - Check if it's already saved in Readwise
   - If it's new, save it to Readwise with the emoji's specific tag
   - Post a custom confirmation message in the thread

### 2. Querying Articles by Tag and Date
1. Send a message containing a date (e.g., "Show me articles since January 1st" or "Get articles from last week")
2. React to the message with one of your configured emojis
3. The bot will:
   - Extract the date from your message
   - Query Readwise for all articles tagged with that emoji's label since the specified date
   - Return a list of articles including:
     - Title
     - Added date
     - Summary
     - URL (if available)

Example:
```
You: Show me articles since March 1st
[React with :brain: emoji]
Bot: Here are the articles tagged with 'Study Material' since 2024-03-01:

*Introduction to Machine Learning*
Added on: 2024-03-15
Summary: A comprehensive guide to the basics of machine learning, covering supervised and unsupervised learning...
URL: https://example.com/ml-intro

*Python Best Practices*
Added on: 2024-03-10
Summary: An in-depth look at Python coding standards and best practices...
URL: https://example.com/python-best-practices
```

## Installation
To add the application to Slack, you *must* have deployed the back-end on Railway using the process above.

Once this is complete, you can create an application on your [Slack workspace](https://api.slack.com/) (you will need administrator permissions).

Required Slack Bot Permissions:
- **channels:history** - To read message content
- **chat:write** - To post confirmation messages
- **reactions:read** - To detect emoji reactions

Configuration Steps:
1. Create a new Slack App in your workspace
2. In "OAuth & Permissions":
   - Add the required bot permissions listed above
   - Install the app to your workspace
   - Copy the Bot User OAuth Token (this is your SLACK_BOT_TOKEN)
3. In "Event Subscriptions":
   - Enable events
   - Add your full application URL as the request URL (format: https://your-app.railway.app/slack/events)
   - Subscribe to the "reaction_added" bot event
4. Get your [Readwise API key](https://readwise.io/access_token)
5. Add all environment variables to your Railway application
6. Invite your bot to desired Slack channels

Test the integration by reacting to a message containing a URL with one of your configured emojis. You should see:
- A confirmation message in the Slack thread
- The article appear in your Readwise Reader with the emoji's specific tag

## Local Development
1. Clone this repository
2. Create a `.env` file with the required environment variables (see above)
3. Install dependencies: `pip install -r requirements.txt`
4. Run the application: `python main.py`

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

## License
This project is licensed under the Apache 2.0 License.
