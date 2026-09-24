"""Constants for the InPost Paczki integration."""
DOMAIN = "inpost_paczki"

# The consumer API used by the InPost Mobile app (Poland).
API_BASE_URL = "https://api-inmobile-pl.easypack24.net"
ENDPOINT_TOKEN = "/global/oauth2/token"
ENDPOINT_ME = "/global/api/v1/user-catalogue/people/me"
ENDPOINT_TRACKED = "/v4/parcels/tracked"
ENDPOINT_NOTIFICATIONS = "/v3/notifications"

# Login happens in the user's browser on InPost's own pages (phone number, SMS
# code, captcha). The app uses OAuth2 authorization code + PKCE with this public
# client; the browser ends up on the callback URL, which the user pastes back.
OAUTH_AUTHORIZE_URL = "https://account.inpost-group.com/oauth2/authorize"
OAUTH_REDIRECT_URI = "https://account.inpost-group.com/callback"
OAUTH_CLIENT_ID = "inpost-mobile"

# The API only answers requests that look like they come from the app.
APP_ID = "pl.inpost.inpostmobile"
USER_AGENT = "InPost-Mobile/4.19.0 (4)-release (iOS 26.7; iPhone14,3; pl)"

CONF_DEVICE_UID = "device_uid"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
CONF_PERSON_ID = "person_id"
CONF_PHONE = "phone"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SHOW_CODES = "show_codes"

# Polling cadence, in minutes. Parcels move a few times a day; five minutes is
# quick enough for "your parcel is in the locker" and light on the API.
DEFAULT_SCAN_INTERVAL = 5
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 60

# Pickup codes open the locker, so they are opt-in: states and attributes end
# up in the recorder database and in anything that reads it.
DEFAULT_SHOW_CODES = False
