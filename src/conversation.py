from telegram import Update, File
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import MessageEntityType, ParseMode

import asyncio

import traceback
import pandas as pd

from loguru import logger

import io
from pyzbar.pyzbar import decode, Decoded
from PIL import Image

from datetime import datetime
import gspread
from gspread_dataframe import set_with_dataframe
from gspread_formatting import *

from nalog import NalogRuPython

from enums import ConversationEnum

from settings import SheetsAccJson

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

async def CancelHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info((
        f"Got cancel command from {update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    context.user_data.clear()
    await update.message.reply_markdown(TextCancel)
    return ConversationHandler.END

async def MissHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info((
        f"Got missing message from {update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))

    if 'link' in context.user_data and 'files' not in context.user_data:
        await update.message.reply_markdown(TextMissStatePhoto)
        return ConversationEnum.AWAIT_LINK_PHOTO

    if 'files' in context.user_data and 'link' not in context.user_data:
        await update.message.reply_markdown(TextMissStateLink)
        return ConversationEnum.AWAIT_LINK_PHOTO
    
    await update.message.reply_markdown(TextMissStateEmpty)
    return ConversationHandler.END

async def FlowHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info((
        f"Got flow message from "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))

    if context.user_data is None:
        context.user_data = {}

    for entity in update.message.entities:
        if entity.type == MessageEntityType.URL:
            context.user_data['link'] = update.message.parse_entity(entity)
            logger.info((
                f"Got link from "
                f"{update.effective_user.id} aka {update.effective_user.name} "
                f"in {update.effective_chat.id} aka {update.effective_chat.title}"
            ))
            break
    for entity in update.message.caption_entities:
        if entity.type == MessageEntityType.URL:
            context.user_data['link'] = update.message.parse_caption_entity(entity)
            logger.info((
                f"Got link from "
                f"{update.effective_user.id} aka {update.effective_user.name} "
                f"in {update.effective_chat.id} aka {update.effective_chat.title}"
            ))
            break
    
    file: File|None = None
    if len(update.message.photo) > 0:
        file  = await update.message.photo[-1].get_file()
    if update.message.document != None:
        file  = await update.message.document.get_file()
    
    if file != None:
        files: list[File] = context.user_data['files'] if 'files' in context.user_data else []
        if file.file_unique_id not in [file.file_unique_id for file in files]:
            logger.info((
                f"Got photo from "
                f"{update.effective_user.id} aka {update.effective_user.name} "
                f"in {update.effective_chat.id} aka {update.effective_chat.title}"
            ))
            context.user_data['files'] = files + [file]
            logger.info((
                f"Number of files is {len(context.user_data['files'])} "
                f"{update.effective_user.id} aka {update.effective_user.name} "
                f"in {update.effective_chat.id} aka {update.effective_chat.title}"
            ))

    if 'link' not in context.user_data and 'files' in context.user_data:
        await update.message.reply_markdown(TextSendLink)
        return ConversationEnum.AWAIT_LINK_PHOTO

    if 'link' in context.user_data and 'files' not in context.user_data:
        await update.message.reply_markdown(TextSendPhoto)
        return ConversationEnum.AWAIT_LINK_PHOTO
    
    return await ProceedHandler(update, context)

async def ProceedHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'link' not in context.user_data or 'files' not in context.user_data:
        await update.message.reply_markdown(TextProceedNoState)
        return ConversationEnum.AWAIT_LINK_PHOTO

    logger.info((
        f"Start processing qr codes task for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    if 'already_start_processing' not in context.user_data:
        context.user_data['already_start_processing'] = True
        await update.message.reply_markdown(TextStartProcessing)

    qr_codes  = context.user_data['qr_codes'] if 'qr_codes' in context.user_data else []
    for file in context.user_data['files']:
        file: File
        try:
            in_memory = io.BytesIO()
            await file.download_to_memory(in_memory)
            in_memory.seek(0)

            qr_decoded: list[Decoded] = decode(Image.open(in_memory))
            qr_bytes: bytes = qr_decoded[0].data
            qr_code: str = qr_bytes.decode("utf-8")
            qr_codes += [qr_code]
        except Exception:
            logger.info((
                f"Got an error while processing qr code in "
                f"{update.effective_user.id} aka {update.effective_user.name} "
                f"in {update.effective_chat.id} aka {update.effective_chat.title}"
            ))
            
            del context.user_data['already_start_processing']
            files: list[File] = context.user_data['files']
            files.remove(file)
            context.user_data['files'] = files

            await update.message.reply_photo(file.file_id, caption=TextQrCodeError, parse_mode=ParseMode.MARKDOWN)
            logger.debug(traceback.format_exc())
            return ConversationEnum.AWAIT_LINK_PHOTO
        
    context.user_data['qr_codes'] = qr_codes
    logger.info((
        f"Number of qr codes {len(context.user_data['qr_codes'])} "
        f"and number of files {len(context.user_data['files'])} "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))

    logger.info((
        f"Done processing qr codes task and asked for phone for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    
    if 'nalog' in context.user_data:
        return await qr_to_spreadsheet(update, context)

    await update.message.reply_markdown(TextSendPhone)
    return ConversationEnum.AWAIT_PHONE

async def SetPhoneCommandHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info((
        f"Seted that user has to print phone for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    await update.message.reply_markdown(TextSendPhone)
    return ConversationEnum.AWAIT_PHONE

async def PhoneHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info((
        f"Got phone number for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    phone = update.message.text
    if phone in ["", None]:
        phone = update.message.caption
    context.user_data['nalog'] = NalogRuPython(phone, line_login=False)
    logger.info((
        f"Created Nalog instance for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    await update.message.reply_markdown(TextSendCode)
    return ConversationEnum.AWAIT_CODE

async def CodeHandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info((
        f"Got sms code for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    code = update.message.text
    if code in ["", None]:
        code = update.message.caption
    nalog: NalogRuPython = context.user_data['nalog']

    try:
        nalog.set_session_id(code)
    except Exception:
        logger.info((
            f"Got an error while setting session id at Nalog instance for "
            f"{update.effective_user.id} aka {update.effective_user.name} "
            f"in {update.effective_chat.id} aka {update.effective_chat.title}"
        ))
        await update.message.reply_markdown(TextCodeError)
        logger.exception(traceback.format_exc())
        return ConversationEnum.AWAIT_CODE

    logger.info((
        f"Set session id for Nalog instance for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title} "
    ))
    
    if 'qr_codes' not in context.user_data or len(context.user_data['qr_codes']) == 0:
        await update.message.reply_markdown(TextSendLinkPhoto)
        return ConversationEnum.AWAIT_LINK_PHOTO
    
    return await qr_to_spreadsheet(update, context)

async def qr_to_spreadsheet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nalog: NalogRuPython = context.user_data['nalog']

    logger.info((
        f"Starting processing qr data to shpreadsheet for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    await update.message.reply_markdown(TextGettingCheques)

    files: list[File]   = context.user_data['files']
    qr_codes: list[str] = context.user_data['qr_codes']

    fullSum = 0
    fullNds = 0
    df_tickets = pd.DataFrame()
    df_items   = pd.DataFrame()
    for file, qr_code in zip(files, qr_codes):
        try:
            ticket = nalog.get_ticket(qr_code)

            ticket_dict: dict[str, int] = ticket['ticket']['document']['receipt']
            df_ticket = pd.DataFrame([{
                'Дата': datetime.fromtimestamp(ticket_dict['dateTime']).strftime("%d.%m.%Y %H:%M"),
                'Сумма': ticket_dict['totalSum'] / 100,
                'Продавец': ticket_dict['user'],
                'Адрес': ticket_dict['retailPlaceAddress'] if 'retailPlaceAddress' in ticket_dict else '',
                'НДС': sum([
                    nds / 100
                    for key, nds in ticket_dict.items()
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
            logger.info((
                f"Got an error while getting ticket data for "
                f"{update.effective_user.id} aka {update.effective_user.name} "
                f"in {update.effective_chat.id} aka {update.effective_chat.title}"
            ))

            await update.message.reply_photo(file.file_id, caption=TextTicketError, parse_mode=ParseMode.MARKDOWN)
            logger.debug(traceback.format_exc())
            continue

    df_head = pd.DataFrame([{
        'Общая сумма': fullSum,
        'Общий НДС':   fullNds,
    }])

    logger.info((
        f"Starting converting tickets to spreadsheet for "
        f"{update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    await update.message.reply_markdown(TextConvertingToSpreadsheet)
    
    try:
        Gspread = gspread.service_account_from_dict(SheetsAccJson)
        sheet = Gspread.open_by_url(context.user_data['link'])
    except Exception:
        logger.info(
            f"Got an exeption while connecting to google for "
            f"{update.effective_user.id} aka {update.effective_user.name} "
            f"in {update.effective_chat.id} aka {update.effective_chat.title}"
        )
        await update.message.reply_markdown(TextSheetError)
        del context.user_data['link']
        logger.exception(traceback.format_exc())
        return ConversationEnum.AWAIT_LINK_PHOTO
    
    try:
        title = TitleBase.format(date = datetime.now().strftime("%d.%m.%Y %H:%M"))
        worksheet = sheet.add_worksheet(title=title,
                                        rows=df_head.shape[0]+df_tickets.shape[0]+df_items.shape[0]+7,
                                        cols=df_items.shape[1])
    except Exception:
        logger.info((
            f"Got an exeption while creating worksheet with title {title} for "
            f"{update.effective_user.id} aka {update.effective_user.name} "
            f"in {update.effective_chat.id} aka {update.effective_chat.title}"
        ))
        await update.message.reply_markdown(TextWorksheetError.format(title=title))
        del context.user_data['link']
        logger.exception(traceback.format_exc())
        return ConversationEnum.AWAIT_LINK_PHOTO

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
        a1_tickets_end = row_tickets + a1_tickets_str + df_tickets.shape[0]

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
        logger.info((
            f"Got an exeption while adding content for worksheet {title} and droped state for "
            f"{update.effective_user.id} aka {update.effective_user.name} "
            f"in {update.effective_chat.id} aka {update.effective_chat.title}"
        ))
        logger.exception(traceback.format_exc())
        sheet.del_worksheet(worksheet)
        context.user_data.clear()
        await update.message.reply_markdown(TextContentError)
        return ConversationHandler.END
    
    logger.info((
        f"Done parsing json file and created worksheet {title} for "
        f"in {update.effective_user.id} aka {update.effective_user.name} "
        f"in {update.effective_chat.id} aka {update.effective_chat.title}"
    ))
    context.user_data.clear()
    await update.message.reply_markdown(TextDone.format(title=title))
    return ConversationHandler.END