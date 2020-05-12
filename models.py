import json
from sqlalchemy import create_engine
from sqlalchemy import Column, String, Date, Integer, Numeric
from sqlalchemy import MetaData, Table, Boolean


with open('./config.json') as f_config:
    config = json.load(f_config)
    mysql_cfg = config["mysql"]


engine = create_engine('mysql+pymysql://{}:{}@{}/{}'.format(
                        mysql_cfg['user'],
                        mysql_cfg['password'],
                        mysql_cfg['host'],
                        mysql_cfg['db']))
metadata = MetaData(engine)


Ports = Table('ports',metadata,
              Column('id', Integer, primary_key=True),
              Column('port', Integer, nullable=False),
              Column('server_id', String(225)),
              Column('net_id', String(225)),
              Column('router_id', String(225)),
              Column('is_ssh', Boolean))
