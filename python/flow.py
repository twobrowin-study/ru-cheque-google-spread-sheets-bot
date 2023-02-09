from telegram import Update, Message, File
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter
from telegram.constants import MessageEntityType, ParseMode

import asyncio

import traceback
import pandas as pd

import io
from pyzbar.pyzbar import decode
from PIL import Image

from datetime import datetime
import gspread
from gspread_dataframe import set_with_dataframe
from gspread_formatting import *

from nalog import NalogRuPython

from settings import SheetsAccJson, SleepSec
from log import Log

from text import (
    TitleBase,
    TextCancel,

    TextMissStateEmpty,
    TextMissStateLink,
    TextMissStatePhoto,

    TextSendLinkPhoto,
    TextSendLink,
    TextSendPhoto,
    TextSendPhone,
    TextSendCode,

    TextGettingCheques,
    TextConvertingToSpreadsheet,
    TextDone,

    TextStartProcessing,

    TextProceedNoState,
    TextQrCodeError,

    TextCodeError,
    TextTicketError,
    TextSheetError,
    TextWorksheetError,
    TextContentError
)

State = pd.DataFrame(data=[], columns=['id', 'link', 'files', 'tasked', 'qr_codes', 'has_to_print_phone', 'nalog'])

class UserHasToPrintPhoneClass(MessageFilter):
    def filter(self, message: Message) -> bool:
        global State
        return not State.loc[
            (State.id == message.chat_id) &
            (
                (
                    (State.qr_codes.str.len() > 0) &
                    (State.nalog.isnull())
                ) |
                (State.has_to_print_phone == True)
            ) 
        ].empty

class UserHasToPrintCodeClass(MessageFilter):
    def filter(self, message: Message) -> bool:
        global State
        return not State.loc[
            (State.id == message.chat_id) &
            (State.nalog.notnull())
        ].empty

UserHasToPrintPhoneFilter = UserHasToPrintPhoneClass()
UserHasToPrintCodeFilter  = UserHasToPrintCodeClass()

async def CancelHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Log.infor(
        f"Got cancel command from {update.effective_user.id} aka {update.effective_user.name}",
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    )
    global State
    State = State.drop(State[State.id == update.effective_chat.id].index)
    await update.message.reply_markdown(TextCancel)

async def MissHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global State
    chat_id = update.effective_chat.id
    Log.infor(
        f"Got missing message from {update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}"
    )

    if not State.loc[(State.id == chat_id) & (State.files.str.len() == 0) & (State.link != "")].empty:
        await update.message.reply_markdown(TextMissStatePhoto)
        return

    if not State.loc[(State.id == chat_id) & (State.files.str.len() > 0) & (State.link == "")].empty:
        await update.message.reply_markdown(TextMissStateLink)
        return
    
    await update.message.reply_markdown(TextMissStateEmpty)

async def FlowHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global State
    chat_id = update.effective_chat.id
    Log.infor(
        f"Got flow message from",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}"
    )

    if State.loc[State.id == chat_id].empty:
        State = pd.concat([
            State,
            pd.DataFrame([{
                'id':       chat_id,
                'link':     "",
                'files':    [],
                'tasked':   False,
                'qr_codes': [],
                'has_to_print_phone': False,
                'nalog':    None,
            }])
        ], ignore_index=True)

    for entity in update.message.entities:
        if entity.type == MessageEntityType.URL:
            State.loc[State.id == chat_id, 'link'] = update.message.parse_entity(entity)
            break
    for entity in update.message.caption_entities:
        if entity.type == MessageEntityType.URL:
            State.loc[State.id == chat_id, 'link'] = update.message.parse_caption_entity(entity)
            break
    
    if (
        len(update.message.photo) > 0 or update.message.document != None
    ) and State.loc[State.id == chat_id].iloc[0].tasked == False:
        await update.message.reply_markdown(TextStartProcessing)

    file = None
    if len(update.message.photo) > 0:
        file  = await update.message.photo[-1].get_file()
    if update.message.document != None:
        file  = await update.message.document.get_file()
    
    if file != None:
        files = State.loc[State.id == chat_id].iloc[0].files
        if file.file_unique_id not in [file.file_unique_id for file in files]:
            State.loc[State.id == chat_id, 'files'] = [files + [file]]

    if not State.loc[(State.id == chat_id) & (State.files.str.len() > 0) & (State.link == "")].empty:
        await update.message.reply_markdown(TextSendLink)
        return

    if not State.loc[(State.id == chat_id) & (State.files.str.len() == 0) & (State.link != "")].empty:
        await update.message.reply_markdown(TextSendPhoto)
        return
    
    if State.loc[State.id == chat_id].iloc[0].tasked == False:
        State.loc[State.id == chat_id, 'tasked'] = True
        context.application.create_task(await_proceed(update, context))

async def await_proceed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    Log.infor(
        f"Awaiting before processing qr codes task for",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}",
    )    
    await asyncio.sleep(SleepSec)
    await ProceedHandler(update, context)

async def ProceedHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global State
    chat_id = update.effective_chat.id

    if State[State.id == chat_id].empty:
        await update.message.reply_markdown(TextProceedNoState)
        return

    Log.infor(
        f"Start processing qr codes task for",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}",
    )

    qr_codes = []
    for file in State.loc[State.id == chat_id].iloc[0].files:
        file: File
        try:
            in_memory = io.BytesIO()
            await file.download_to_memory(in_memory)
            in_memory.seek(0)

            qr_decoded = decode(Image.open(in_memory))
            qr_code: str = qr_decoded[0].data.decode("utf-8")
            qr_codes += [qr_code]
        except Exception:
            Log.infor(
                f"Got an error while processing qr code in",
                f"{update.effective_user.id} aka {update.effective_user.name}",
                f"in {chat_id} aka {update.effective_chat.title}",
            )
            
            files = State.loc[State.id == chat_id].iloc[0].files
            files.remove(file)
            State.loc[State.id == chat_id, 'files'] = [files]
            State.loc[State.id == chat_id, 'tasked'] = False

            await update.message.reply_photo(file.file_id, caption=TextQrCodeError, parse_mode=ParseMode.MARKDOWN)
            Log.debug(traceback.format_exc())
            return
        
    State.loc[State.id == chat_id, 'qr_codes'] = [qr_codes]
    
    if State.loc[State.id == chat_id].iloc[0].nalog != None:
        return await qr_to_spreadsheet(update, context)

    await update.message.reply_markdown(TextSendPhone)
    Log.infor(
        f"Done processing qr codes task and asked for phone for",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}",
    )

async def SetPhoneCommandHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global State
    chat_id = update.effective_chat.id
    if State.loc[State.id == chat_id].empty:
        State = pd.concat([
            State,
            pd.DataFrame([{
                'id':       chat_id,
                'link':     "",
                'files':    [],
                'tasked':   False,
                'qr_codes': [],
                'has_to_print_phone': True,
                'nalog':    None,
            }])
        ], ignore_index=True)
    else:
        State.loc[State.id == chat_id, 'has_to_print_phone'] = True
    Log.infor(
        f"Seted that user has to print phone for",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}",
    )
    await update.message.reply_markdown(TextSendPhone)

async def PhoneHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global State
    chat_id = update.effective_chat.id
    phone = update.message.text
    if phone in ["", None]:
        phone = update.message.caption
    State.loc[State.id == chat_id, 'nalog'] = NalogRuPython(phone, line_login=False)
    State.loc[State.id == chat_id, 'has_to_print_phone'] = False
    Log.infor(
        f"Created Nalog instance for",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}",
    )
    await update.message.reply_markdown(TextSendCode)

async def CodeHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global State
    chat_id = update.effective_chat.id
    code = update.message.text
    if code in ["", None]:
        code = update.message.caption
    nalog: NalogRuPython = State.loc[State.id == chat_id].iloc[0].nalog

    try:
        nalog.set_session_id(code)
    except Exception:
        Log.infor(
            f"Got an error while setting session id at Nalog instance for",
            f"{update.effective_user.id} aka {update.effective_user.name}",
            f"in {chat_id} aka {update.effective_chat.title}",
        )
        await update.message.reply_markdown(TextCodeError)
        Log.debug(traceback.format_exc())
        return

    Log.infor(
        f"Set session id for Nalog instance for",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}",
    )
    
    if len(State.loc[State.id == chat_id].iloc[0].qr_codes) == 0:
        await update.message.reply_markdown(TextSendLinkPhoto)
        return
    
    await qr_to_spreadsheet(update, context)

async def qr_to_spreadsheet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global State
    chat_id = update.effective_chat.id
    nalog: NalogRuPython = State.loc[State.id == chat_id].iloc[0].nalog

    Log.infor(
        f"Starting processing qr data to shpreadsheet for",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}",
    )
    await update.message.reply_markdown(TextGettingCheques)

    files    = State.loc[State.id == chat_id].iloc[0].files
    qr_codes = State.loc[State.id == chat_id].iloc[0].qr_codes

    fullSum = 0
    fullNds = 0
    df_tickets = pd.DataFrame()
    df_items = pd.DataFrame()
    for file,qr_code in zip(files, qr_codes):
        try:
            ticket = nalog.get_ticket(qr_code)
        
            ticket_dict = ticket['ticket']['document']['receipt']
            df_ticket = pd.DataFrame([{
                'Дата': datetime.utcfromtimestamp(ticket_dict['dateTime']).strftime("%d.%m.%Y %H:%M"),
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
                'Включить в общий счёт': 'Да'
            } for item in ticket_dict['items']])

            fullSum += df_ticket.iloc[0]['Сумма']
            fullNds += df_ticket.iloc[0]['НДС']
            
            df_tickets = pd.concat([df_tickets, df_ticket], ignore_index=True)
            df_items = pd.concat([df_items, df_items_in_ticket], ignore_index=True)
        
        except Exception:
            Log.infor(
                f"Got an error while getting ticket data for",
                f"{update.effective_user.id} aka {update.effective_user.name}",
                f"in {chat_id} aka {update.effective_chat.title}",
            )

            await update.message.reply_photo(file.file_id, caption=TextTicketError, parse_mode=ParseMode.MARKDOWN)
            Log.debug(traceback.format_exc())
            continue

    df_head = pd.DataFrame([{
        'Общая сумма': fullSum,
        'Общий НДС':   fullNds,
    }])

    Log.infor(
        f"Starting converting tickets to spreadsheet for",
        f"{update.effective_user.id} aka {update.effective_user.name}",
        f"in {chat_id} aka {update.effective_chat.title}",
    )
    await update.message.reply_markdown(TextConvertingToSpreadsheet)
    
    try:
        Gspread = gspread.service_account_from_dict(SheetsAccJson)
        sheet = Gspread.open_by_url(State.loc[State.id == chat_id].iloc[0].link)
    except Exception:
        Log.infor(
            f"Got an exeption while connecting to google for",
            f"{update.effective_user.id} aka {update.effective_user.name}",
            f"in {chat_id} aka {update.effective_chat.title}",
        )
        await update.message.reply_markdown(TextSheetError)
        State.loc[State.id == chat_id, 'link'] = ""
        Log.exception(traceback.format_exc())
        return
    
    try:
        title = TitleBase.format(date = datetime.now().strftime("%d.%m.%Y %H:%M"))
        worksheet = sheet.add_worksheet(title=title, rows=100, cols=20)
    except Exception:
        Log.infor(
            f"Got an exeption while creating worksheet with title {title} for",
            f"{update.effective_user.id} aka {update.effective_user.name}",
            f"in {chat_id} aka {update.effective_chat.title}",
        )
        await update.message.reply_markdown(TextWorksheetError.format(title=title))
        State.loc[State.id == chat_id, 'link'] = ""
        Log.exception(traceback.format_exc())
        return

    try:
        next_avaliable_row = lambda: len( list( filter(None, worksheet.col_values(1)) ) ) + 1
        set_with_dataframe(worksheet, df_head,  row = 1, col = 1, include_index = False)

        row_tickets = 1 + next_avaliable_row()
        set_with_dataframe(worksheet, df_tickets, row = row_tickets, col = 1, include_index = False)
        
        row_items = 1 + next_avaliable_row() + 1
        set_with_dataframe(worksheet, df_items, row = row_items, col = 1, include_index = False)

        row_formula = 1 + next_avaliable_row() + 1

        a1_formula   = row_formula + 1
        ai_itmes_str = row_items   + 1
        ai_itmes_end = row_items   + df_items.shape[0]
        worksheet.update(
            f"C{a1_formula}:D{a1_formula}", [[
                "Общий счёт",
                f"=СУММЕСЛИ(E{ai_itmes_str}:E{ai_itmes_end};\"=Да\";D{ai_itmes_str}:D{ai_itmes_end})"
            ]],
            raw = False
        )

        a1_tickets_str = row_tickets + 1
        a1_tickets_end = row_tickets + df_items.shape[0]

        fmt = CellFormat(horizontalAlignment='CENTER',textFormat=TextFormat(bold=True))
        format_cell_ranges(worksheet, [
            (f"A1:B1", fmt),
            (f"A{row_tickets}:E{row_tickets}", fmt),
            (f"A{row_items}:E{row_items}", fmt),
            (f"C{a1_formula}:C{a1_formula}", fmt),
            (f"A{a1_tickets_str}:E{a1_tickets_end}", CellFormat(wrapStrategy='WRAP')),
        ])
        set_column_width(worksheet, 'A', 450)
        set_column_width(worksheet, 'C', 200)
        set_column_width(worksheet, 'D', 200)
        set_column_width(worksheet, 'E', 200)
    except Exception:
        Log.infor(
            f"Got an exeption while adding content for worksheet {title} and droped state for",
            f"{update.effective_user.id} aka {update.effective_user.name}",
            f"in {chat_id} aka {update.effective_chat.title}",
        )
        Log.exception(traceback.format_exc())
        sheet.del_worksheet(worksheet)
        State = State.drop(State[State.id == update.effective_chat.id].index)
        await update.message.reply_markdown(TextContentError.format(title=title))
        return
    
    Log.infor(
        f"Done parsing json file and created worksheet {title} for",
        f"in {update.effective_user.id} aka {update.effective_user.name}",
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    )
    State = State.drop(State[State.id == update.effective_chat.id].index)
    await update.message.reply_markdown(TextDone.format(title=title))