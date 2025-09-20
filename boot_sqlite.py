import sys, pysqlite3
sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")