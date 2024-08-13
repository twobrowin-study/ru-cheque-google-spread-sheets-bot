from telegram import Bot, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler
)
from telegram.ext.filters import (
    Entity,
    PHOTO,
    ALL,
    TEXT
)
from telegram.constants import MessageEntityType
from loguru import logger

from settings import BotToken
from text import TitleBase, HelpText

from enums import ConversationEnum
from conversation import (
    CancelHandler,
    FlowHandler,
    ProceedHandler,
    SetPhoneCommandHandler,
    PhoneHandler,
    CodeHandler,
    MissHandler,
)

async def StartHelpHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(
        f"Got start or help command from {update.effective_user.id} aka {update.effective_user.name}"
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    )
    await update.message.reply_markdown(
        HelpText.format(
            title = TitleBase.format(date = '<Сегодняшняя дата и время>')
        )
    )

async def post_init(app: Application) -> None:
    bot: Bot = app.bot
    await bot.set_my_commands([
        ("help",    "Получить помощь"),
        ("cancel",  "Отменить текущие операции"),
        ("proceed", "Продолжить расшифровывать qr коды несмотря на предыдущие ошибки"),
        ("phone",   "Ввести номер телефона и провести регистрацию KKT Nalog"),
    ])

if __name__ == '__main__':
    logger.info("Starting...")
    app = ApplicationBuilder().token(BotToken).post_init(post_init).build()

    app.add_handlers([
        CommandHandler("start", StartHelpHandler),
        CommandHandler("help",  StartHelpHandler),
        CommandHandler("cancel", CancelHandler)
    ])

    app.add_handler(ConversationHandler(
        entry_points = [
            MessageHandler(Entity(MessageEntityType.URL) | PHOTO, FlowHandler),
            CommandHandler("proceed", ProceedHandler),
            CommandHandler("phone", SetPhoneCommandHandler),
        ],
        states = {
            ConversationEnum.AWAIT_LINK_PHOTO: [
                MessageHandler(Entity(MessageEntityType.URL) | PHOTO, FlowHandler),
                CommandHandler("proceed", ProceedHandler),
                CommandHandler("phone", SetPhoneCommandHandler),
            ],
            ConversationEnum.AWAIT_PHONE: [
                CommandHandler("phone", SetPhoneCommandHandler),
                MessageHandler(PHOTO, FlowHandler),
                MessageHandler(TEXT,  PhoneHandler),
            ],
            ConversationEnum.AWAIT_CODE: [
                CommandHandler("phone", SetPhoneCommandHandler),
                MessageHandler(TEXT, CodeHandler)
            ]
        },
        fallbacks = [
            CommandHandler("cancel", CancelHandler),
            MessageHandler(ALL, MissHandler)
        ]
    ))

    app.run_polling()
    logger.info("Exit. Goodby!")