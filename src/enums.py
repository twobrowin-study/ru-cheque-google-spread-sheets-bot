from enum import Enum
from telegram.ext import ConversationHandler

class ConversationEnum(Enum):
    AWAIT_LINK_PHOTO = 1
    AWAIT_PHONE = 2
    AWAIT_CODE = 3