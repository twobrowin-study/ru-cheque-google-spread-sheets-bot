import logging

Log = logging.getLogger("logging_tryout2")
ch = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s; %(levelname)s; %(message)s",
                              "%Y-%m-%d %H:%M:%S")
ch.setFormatter(formatter)
Log.addHandler(ch)

Log.setLevel(logging.DEBUG)
Log.infor = lambda *x: Log.info(" ".join(x))