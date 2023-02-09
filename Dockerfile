FROM python:3.10-slim-buster

ENV BOT_TOKEN ''
ENV SHEETS_ACC_JSON ''
ENV SLEEP_SEC '1'

WORKDIR /python-docker

RUN apt update -y && \
    apt install -y libzbar0
COPY requirenments.txt .
RUN pip3 install -r requirenments.txt

COPY python/*.py ./

CMD [ "python3", "-u", "main.py"]