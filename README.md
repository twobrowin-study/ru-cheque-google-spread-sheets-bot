# Бот обработчки чеков РФ

## Локальный запуск

Следует скопировать и заполнить содержимое `.env.example` как файл `.env`

В директории `src` следует выполнить `python main.py`

## Сборка

```bash
docker build . --push -t twobrowin/ru-cheque-google-spread-sheets-bot:<version>
```

## Развёртывание

```bash
helm upgrade --install --debug -n public ru-cheque-google-spread-sheets-bot ./charts
```

## Зависимости k8s

Следует создать неймспейс `public` и секрет `ru-cheque-google-spread-sheets-bot` в нём, поля секрета:

* `bot_token` - токен подключения к Telegram боту

* `sheets_acc_json` - JWT токен подключения к Google Spreadsheet API
