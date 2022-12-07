from telegram import Bot, Update
from telegram.ext import ContextTypes
from telegram.ext import Application, ApplicationBuilder
from telegram.ext import CommandHandler, MessageHandler

from settings import BotToken
from log import Log

from flow import TitleBase

from flow import StateAwaitFileFilter
from flow import StateAwaitLinkFilter
from flow import MessageHasJsonFileFilter
from flow import MessageHasLinkFilter
from flow import CancelHandler
from flow import JsonFileHandler
from flow import NotJsonFileHandler
from flow import LinkHandler
from flow import NotLinkHandler

HelpText = """
Привет! Как же хорошо, что ты решил воспользоваться моими услугами!

Отправь мне файл чека, который ты можешь получить из приложения *Проверка чека* ФНС РФ.

А потом ссылку на Google таблицу, в которую нужно этот чек добавить. Ссылка обязательно должна быть с доступом на редактирование!

Я создам новую страницу с названием `{title}` и добавлю туда информацию из чека.
Если в файле было несколько чеков - таблицы буду объеденены.

_А ещё я постараюсь перевести названия, помещу в шапку общую информацию и поделю числа на 100 чтобы получились рубли._
"""

async def StartHelpHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Log.info(f"Got start or help command from {update.effective_user.id} aka {update.effective_user.name} " +\
        f"in {update.effective_chat.id} aka {update.effective_chat.title}")
    await update.message.reply_markdown(
        HelpText.format(
            title = TitleBase.format(date = '<Сегодняшняя дата и время>')
        )
    )

async def post_init(app: Application) -> None:
    bot: Bot = app.bot
    await bot.set_my_commands([
        ("help",   "Получить помощь"),
        ("cancel", "Отменить текущие операции"),
    ])

if __name__ == '__main__':
    Log.info("Starting...")
    app = ApplicationBuilder().token(BotToken).post_init(post_init).build()

    app.add_handler(CommandHandler("start", StartHelpHandler))
    app.add_handler(CommandHandler("help",  StartHelpHandler))

    app.add_handler(CommandHandler("cancel", CancelHandler))

    app.add_handler(MessageHandler(StateAwaitFileFilter & MessageHasJsonFileFilter, JsonFileHandler))
    app.add_handler(MessageHandler(StateAwaitFileFilter, NotJsonFileHandler))

    app.add_handler(MessageHandler(StateAwaitLinkFilter & MessageHasLinkFilter, LinkHandler))
    app.add_handler(MessageHandler(StateAwaitLinkFilter, NotLinkHandler))

    app.run_polling()
    Log.info("Exit. Goodby!")