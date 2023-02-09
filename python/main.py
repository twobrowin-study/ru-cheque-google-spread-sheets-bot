from telegram import Bot, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
)
from telegram.ext.filters import (
    Entity,
    PHOTO,
    ALL
)
from telegram.constants import MessageEntityType

from settings import BotToken
from log import Log

from text import TitleBase, HelpText


from flow import (
    UserHasToPrintPhoneFilter,
    UserHasToPrintCodeFilter
)
from flow import (
    CancelHandler,
    FlowHandler,
    ProceedHandler,
    SetPhoneCommandHandler,
    PhoneHandler,
    CodeHandler,
    MissHandler,
)

async def StartHelpHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Log.infor(
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
    Log.info("Starting...")
    app = ApplicationBuilder().token(BotToken).post_init(post_init).build()

    app.add_handler(CommandHandler("start", StartHelpHandler))
    app.add_handler(CommandHandler("help",  StartHelpHandler))

    app.add_handler(CommandHandler("cancel",  CancelHandler))
    app.add_handler(CommandHandler("proceed", ProceedHandler))
    app.add_handler(CommandHandler("phone",   SetPhoneCommandHandler))

    app.add_handler(MessageHandler(Entity(MessageEntityType.URL) | PHOTO, FlowHandler))
    app.add_handler(MessageHandler(UserHasToPrintPhoneFilter, PhoneHandler))
    app.add_handler(MessageHandler(UserHasToPrintCodeFilter,  CodeHandler))
    app.add_handler(MessageHandler(ALL, MissHandler))

    app.run_polling()
    Log.info("Exit. Goodby!")