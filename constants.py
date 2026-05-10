from datetime import timedelta, timezone

PLUGIN_NAME = "astrbot_plugin_nikke_news"
OFFICIAL_PLATE_ID = 43
POST_LIST_URL = (
    "https://api.blablalink.com/api/ugc/direct/standalonesite/"
    "Dynamics/GetPostList"
)
PLAYER_PROGRESS_URL = (
    "https://api.blablalink.com/api/game/proxy/"
    "Game/GetUserDailyContentsProgress"
)
GET_USER_CHARACTERS_URL = (
    "https://api.blablalink.com/api/game/proxy/"
    "Game/GetUserCharacters"
)
GET_USER_CHARACTER_DETAILS_URL = (
    "https://api.blablalink.com/api/game/proxy/"
    "Game/GetUserCharacterDetails"
)
POST_DETAIL_URL = "https://www.blablalink.com/post/detail?post_uuid={post_uuid}"
MAX_SEEN_POSTS = 500
SUMMARY_MAX_LENGTH = 300
REQUEST_TIMEOUT_SECONDS = 60
CONTENT_MODES = {"none", "summary", "content"}
SUPPORTED_LANGUAGES = {"zh-TW", "en", "ja", "ko"}
SUPPORTED_TARGET_TYPES = {"GroupMessage", "PrivateMessage", "FriendMessage"}
CST = timezone(timedelta(hours=8))
