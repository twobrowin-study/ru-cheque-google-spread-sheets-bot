FROM python:3.10-slim-buster

WORKDIR /python-docker

COPY requirenments.txt .
RUN pip3 install -r requirenments.txt

COPY python/*.py ./

ENV BOT_TOKEN ''
ENV SHEETS_ACC_JSON ''

CMD [ "python3", "-u", "main.py"]