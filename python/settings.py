from os import environ
import json

BotToken = environ.get('BOT_TOKEN')
if BotToken == '' or BotToken == None:
    with open('telegram.txt', 'r') as fp:
        BotToken = fp.read()

SheetsAccJson = environ.get('SHEETS_ACC_JSON')
if SheetsAccJson == '' or SheetsAccJson == None:
    with open('./serviceacc.json', 'r') as fp:
        SheetsAccJson = json.load(fp)
else:
    SheetsAccJson = json.loads(SheetsAccJson)

SleepSec = int(environ.get('SLEEP_SEC'))