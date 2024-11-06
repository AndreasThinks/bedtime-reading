# Slack Wallabag Integration

This application integrates Slack with Wallabag, allowing you to save URLs shared in Slack to your Wallabag account with customizable reactions and messages.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/AzS2fY?referralCode=mOVLfw)

## Features
- Save URLs shared in Slack to Wallabag when specific emoji reactions are added
- Each emoji reaction saves the article with its specific tag (one tag per article)
- Query articles by tag and date using the `/retrieve-articles` command
- Custom confirmation messages for each emoji reaction
- Configurable newsletter tag for including articles in the newsletter
- Automatic duplicate detection to prevent saving the same article twice
- Configurable rate limiting
- Secure handling of environment variables

## Deployment
Click the "Deploy to Railway" button above to start the deployment process. Don't worry if you don't have all of these yet, you'll get the rest after deploying your Slack App.

Required Environment Variables:
- `SLACK_BOT_TOKEN`: Your Slack Bot Token
- `SLACK_SIGNING_SECRET`: Your Slack Signing Secret
- `WALLABAG_CLIENT_ID`: Your Wallabag Client ID
- `WALLABAG_CLIENT_SECRET`: Your Wallabag Client Secret
- `WALLABAG_USERNAME`: Your Wallabag Username
- `WALLABAG_PASSWORD`: Your Wallabag Password
- `WALLABAG_URL`: Your Wallabag URL (defaults to https://app.wallabag.it)
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts (e.g., your-app-name.railway.app)

Optional Environment Variables:
- `RATE_LIMIT_PER_MINUTE`: Number of requests allowed per minute (default: 20)
- `EMOJI_CONFIGS`: Configuration for emoji reactions in the format "emoji1:label1:message1;emoji2:label2:message2"
- `NEWSLETTER_TAG`: Tag to include in the newsletter (default: "Newsletter")

Example Configuration:

1. Emoji Configuration:
```
EMOJI_CONFIGS=bookmark:Read Later:📚 Added to your reading list;brain:Study Material:🧠 Saved as study material;star:Must Read:⭐ Marked as must-read
```

This creates three different reactions with distinct purposes:
- :bookmark: - Tags articles as "Read Later" for general reading
- :brain: - Tags articles as "Study Material" for learning resources
- :star: - Tags articles as "Must Read" for important content

2. Newsletter Tag:
```
NEWSLETTER_TAGS=must-read
```

This configuration would include articles tagged with the "must-read" tag into the newsletter. You can specify the tag rather than the emoji.

Each article is saved with exactly one tag based on the emoji used. For example:
- Using :bookmark: saves the article with only the "Read Later" tag
- Using :brain: saves the article with only the "Study Material" tag
- Using :star: saves the article with only the "Must Read" tag

If NEWSLETTER_TAG is not set, it defaults to including only articles tagged with "Newsletter".

If EMOJI_CONFIGS is not set, it defaults to using the :bookmark: emoji with a standard message and "Read Later" tag.

## Usage

### 1. Saving URLs to Wallabag
1. Add the Slack bot to your workspace and invite it to the desired channels.
2. When a message containing a URL is posted, react to it with one of your configured emojis.
3. The bot will:
   - Extract the URL from the message
   - Check if it's already saved in Wallabag
   - If it's new, save it to Wallabag with the emoji's specific tag
   - Post a custom confirmation message in the thread

### 2. Retrieving Articles
Use the `/retrieve-articles` command to fetch articles with a specific tag since a given date. The response will only be visible to you.

Command format:
```
/retrieve-articles :emoji: date
```

The emoji must be one of your configured emojis from EMOJI_CONFIGS. The date can be in various formats:

Examples:
```
/retrieve-articles :bookmark: 2024-01-01
/retrieve-articles :brain: last week
/retrieve-articles :star: January 1st
/retrieve-articles :bookmark: 3 days ago
```

Each example will return all articles tagged with that emoji's label (e.g., "Read Later" for :bookmark:) since the specified date.

The response includes:
- Article title
- Date added
- URL

Long responses are automatically split into multiple messages to comply with Slack's message length limits.

## Installation
To add the application to Slack, you *must* have deployed the back-end on Railway using the process above.

Once this is complete, you can create an application on your [Slack workspace](https://api.slack.com/) (you will need administrator permissions).

Required Slack Bot Token Scopes (in OAuth & Permissions):
- **channels:history** - To read message content
- **chat:write** - To post confirmation messages
- **reactions:read** - To detect emoji reactions
- **commands** - To handle slash commands (required for `/retrieve-articles`)

If you're upgrading an existing installation to add the `/retrieve-articles` command:
1. Go to your app's settings at api.slack.com
2. Navigate to "OAuth & Permissions"
3. Under "Scopes", add the "commands" Bot Token Scope
4. Reinstall the app to your workspace to apply the new scope

Configuration Steps:
1. Create a new Slack App in your workspace
2. In "OAuth & Permissions":
   - Add all the required bot token scopes listed above
   - Install the app to your workspace
   - Copy the Bot User OAuth Token (this is your SLACK_BOT_TOKEN)
3. In "Event Subscriptions":
   - Enable events
   - Add your full application URL as the request URL (format: https://your-app.railway.app/slack/events)
   - Subscribe to the "reaction_added" bot event
4. In "Slash Commands":
   - Create a new command called `/retrieve-articles`
   - Set the request URL to: https://your-app.railway.app/slack/events
   - Add a description: "Retrieve articles with a specific tag since a given date"
   - Add usage hint: ":emoji: date (e.g., :bookmark: 2024-01-01)"
5. Set up your Wallabag account and get your client credentials
6. Add all environment variables to your Railway application
7. Invite your bot to desired Slack channels

Test the integration by:
1. Reacting to a message containing a URL with one of your configured emojis. You should see:
   - A confirmation message in the Slack thread
   - The article appear in your Wallabag account with the emoji's specific tag
2. Using the `/retrieve-articles` command with an emoji and date to fetch saved articles. The response will only be visible to you.

## Local Development
1. Clone this repository
2. Create a `.env` file with the required environment variables (see above)
3. Install dependencies: `pip install -r requirements.txt`
4. Run the application: `python main.py`

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

## License
This project is licensed under the Apache 2.0 License.
