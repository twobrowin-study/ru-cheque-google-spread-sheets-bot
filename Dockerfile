FROM python:3.10-slim-buster

ENV BOT_TOKEN ''
ENV SHEETS_ACC_JSON ''

WORKDIR /python-docker

RUN apt update -y && \
    apt install -y libzbar0
COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY src/*.py ./

CMD [ "python3", "-u", "main.py"]