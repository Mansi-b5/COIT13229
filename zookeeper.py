# Used week 7 tutorial as inspiration 
# Wk7_kazoo_ZK.py

from kazoo.client import KazooClient
from kazoo.exceptions import KazooException
import threading
import time, json

class Zookeeper:
    def __init__(self): 
        self.id=threading.get_ident()
        self.zk = KazooClient(hosts='127.0.0.1:2181') 
        self.zk.start()



