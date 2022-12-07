from telegram import Update, Message
from telegram import Document, File
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter
from telegram.constants import MessageEntityType

import traceback
import gspread
from gspread_dataframe import set_with_dataframe
import pandas as pd
from datetime import datetime
import json

from settings import SheetsAccJson
from log import Log

Gspread = gspread.service_account_from_dict(SheetsAccJson)

State = pd.DataFrame(data=[], columns=['id', 'state', 'document'])
STATE_LINK_AWAIT = 'link_await'

TitleBase = "Чек от {date}"

TextCancel = """
Все операции отменены - теперь снова жду от тебя json файл из приложения *Проверка чека*
"""

TextSendLink = """
Супер! Теперь вышли мне ссылку на таблицу Google

_Ссылка должна быть с правами на редактирование!_
"""

TextDone = """
Готово! Я добавил лист `{title}` в таблицу
"""

TextBasicError = """
Произошла какая-то ошибка, попробуй ещё раз

Снова жду от тебя json файл из приложения *Проверка чека*
"""

TextFileError = """
С файлом что-то не так, мне нужен json файл из приложения *Проверка чека*
"""

TextLinkError = """
Со ссылкой какая-то проблема, мне нужна ссылка на Google таблицу
"""

TextSheetError = """
Произошла ошибка при подключении к таблице, пошли ссылку ещё раз

_Ссылка должна быть с правами на редактирование!_
"""

TextWorksheetError = """
Произошла ошибка при создании листа `{title}`, пошли ссылку ещё раз

_Ссылка должна быть с правами на редактирование!_
"""

ParceError = """
Произошла ошибка при парсинге файла

*Я сбросил все операции и жду от тебя json файл*
"""

class StateAwaitFileClass(MessageFilter):
    def filter(self, message: Message) -> bool:
        return State[State.id == message.chat_id].empty
StateAwaitFileFilter = StateAwaitFileClass()

class StateAwaitLinkClass(MessageFilter):
    def filter(self, message: Message) -> bool:
        return not State[(State.id == message.chat_id) & (State.state == STATE_LINK_AWAIT)].empty
StateAwaitLinkFilter = StateAwaitLinkClass()

class MessageHasJsonFileClass(MessageFilter):
    def filter(self, message: Message) -> bool:
        document: Document = message.document
        if document == None:
            return False
        return document.file_name.split('.')[-1] == 'json'
MessageHasJsonFileFilter = MessageHasJsonFileClass()

class MessageHasLinkClass(MessageFilter):
    def filter(self, message: Message) -> bool:
        for entity in message.entities:
            return entity.type == MessageEntityType.URL
        return False
MessageHasLinkFilter = MessageHasLinkClass()

async def CancelHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Log.info(f"Got cancel command from {update.effective_user.id} aka {update.effective_user.name} " +\
        f"in {update.effective_chat.id} aka {update.effective_chat.title}")
    global State
    State = State.drop(State[State.id == update.effective_chat.id].index)
    await update.message.reply_markdown(TextCancel)

async def JsonFileHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Log.info(f"Got json file from {update.effective_user.id} aka {update.effective_user.name} " +\
        f"in {update.effective_chat.id} aka {update.effective_chat.title}")
    global State
    State = pd.concat([
        State,
        pd.DataFrame([{
            'id': update.effective_chat.id,
            'state': STATE_LINK_AWAIT,
            'document': update.message.document
        }])
    ], ignore_index=True)
    await update.message.reply_markdown(TextSendLink)

async def NotJsonFileHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Log.info(f"Got not json file from {update.effective_user.id} aka {update.effective_user.name} " +\
        f"in {update.effective_chat.id} aka {update.effective_chat.title}")
    await update.message.reply_markdown(TextFileError)

async def LinkHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Log.info(f"Got link from {update.effective_user.id} aka {update.effective_user.name} " +\
        f"in {update.effective_chat.id} aka {update.effective_chat.title}")
    try:
        for entity in update.message.entities:
            if entity.type == MessageEntityType.URL:
                sheet = Gspread.open_by_url(update.message.parse_entity(entity))
                break
    except Exception:
        Log.info(f"Got an exeption while parsing url from {update.effective_user.id} aka {update.effective_user.name} " +\
            f"in {update.effective_chat.id} aka {update.effective_chat.title}")
        Log.exception(traceback.format_exc())
        await update.message.reply_markdown(TextSheetError)
        return

    try:
        title = TitleBase.format(date = datetime.now().strftime("%d.%m.%Y %H:%M"))
        worksheet = sheet.add_worksheet(title=title, rows=100, cols=20)
    except Exception:
        Log.info(f"Got an exeption while creating worksheet from {update.effective_user.id} aka {update.effective_user.name} " +\
            f"in {update.effective_chat.id} aka {update.effective_chat.title}")
        Log.exception(traceback.format_exc())
        await update.message.reply_markdown(TextWorksheetError.format(title = title))
        return
    
    global State

    try:
        document: Document = State[State.id == update.effective_chat.id].iloc[0].document
        file: File = await document.get_file()
        content = await file.download_as_bytearray()
        tickets = json.loads(content.decode("utf-8"))

        if type(tickets) != list:
            tickets = [tickets]
        
        fullSum = 0
        fullNds = 0
        df_tickets = pd.DataFrame()
        df_items = pd.DataFrame()

        for ticket in tickets:
            ticket_dict = ticket['ticket']['document']['receipt']
            df_ticket = pd.DataFrame([{
                'Дата': datetime.strptime(ticket_dict['dateTime'], "%Y-%m-%dT%H:%M:%S").strftime("%d.%m.%Y %H:%M"),
                'Сумма': ticket_dict['totalSum'] / 100,
                'Продавец': ticket_dict['user'],
                'Адрес': ticket_dict['retailPlaceAddress'] if 'retailPlaceAddress' in ticket_dict else '',
                'НДС': sum([
                    ticket_dict[key] / 100
                    for key in ticket_dict
                    if key.startswith('nds')
                ]),
            }])

            df_items_in_ticket = pd.DataFrame([{
                'Название': item['name'],
                'Цена': item['price'] / 100,
                'Количество': item['quantity'],
                'Сумма': item['sum'] / 100,
            } for item in ticket_dict['items']])

            fullSum += df_ticket.iloc[0]['Сумма']
            fullNds += df_ticket.iloc[0]['НДС']
            
            df_tickets = pd.concat([df_tickets, df_ticket], ignore_index=True)
            df_items = pd.concat([df_items, df_items_in_ticket], ignore_index=True)

        df_head = pd.DataFrame([{
            'Общая сумма': fullSum,
            'Общий НДС':   fullNds,
        }])

        next_avaliable_row = lambda: len( list( filter(None, worksheet.col_values(1)) ) ) + 1

        set_with_dataframe(worksheet, df_head,  row = 1, col = 1, include_index = False)

        row_tickets = 1 + next_avaliable_row()
        set_with_dataframe(worksheet, df_tickets, row = row_tickets, col = 1, include_index = False)
        
        row_items = 1 + next_avaliable_row() + 1
        set_with_dataframe(worksheet, df_items, row = row_items, col = 1, include_index = False)

    except Exception:
        Log.info(f"Got an exeption while parsing json file but created and droped worksheet {title} and droped state" +\
            "from {update.effective_user.id} aka {update.effective_user.name} " +\
            f"in {update.effective_chat.id} aka {update.effective_chat.title}")
        Log.exception(traceback.format_exc())
        sheet.del_worksheet(worksheet)
        State = State.drop(State[State.id == update.effective_chat.id].index)
        await update.message.reply_markdown(ParceError.format(title = title))
        return

    State = State.drop(State[State.id == update.effective_chat.id].index)
    Log.info(f"Done parsing json file and created worksheet {title} " +\
        "in {update.effective_user.id} aka {update.effective_user.name} " +\
        f"in {update.effective_chat.id} aka {update.effective_chat.title}")
    await update.message.reply_markdown(TextDone.format(title = title))

async def NotLinkHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Log.info(f"Got bad link from {update.effective_user.id} aka {update.effective_user.name} " +\
        f"in {update.effective_chat.id} aka {update.effective_chat.title}")
    await update.message.reply_markdown(TextLinkError)